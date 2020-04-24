import re
import textwrap
from typing import Optional, TYPE_CHECKING, Tuple, Union

from qcodes.instrument.channel import InstrumentChannel
import qcodes.utils.validators as vals

from .KeysightB1500_module import B1500Module, parse_dcorr_query_response, \
    format_dcorr_response, _DCORRResponse
from .message_builder import MessageBuilder
from . import constants
from .constants import ModuleKind, ChNr, MM
if TYPE_CHECKING:
    from .KeysightB1500_base import KeysightB1500


_pattern = re.compile(
    r"((?P<status>\w)(?P<chnr>\w)(?P<dtype>\w))?"
    r"(?P<value>[+-]\d{1,3}\.\d{3,6}E[+-]\d{2})"
)


class B1520A(B1500Module):
    """
    Driver for Keysight B1520A Capacitance Measurement Unit module for B1500
    Semiconductor Parameter Analyzer.

    Args:
        parent: mainframe B1500 instance that this module belongs to
        name: Name of the instrument instance to create. If `None`
            (Default), then the name is autogenerated from the instrument
            class.
        slot_nr: Slot number of this module (not channel number)
    """
    phase_compensation_timeout = 60  # manual says around 30 seconds
    MODULE_KIND = ModuleKind.CMU

    def __init__(self, parent: 'KeysightB1500', name: Optional[str], slot_nr,
                 **kwargs):
        super().__init__(parent, name, slot_nr, **kwargs)

        self.channels = (ChNr(slot_nr),)

        self.add_parameter(
            name="voltage_dc", set_cmd=self._set_voltage_dc, get_cmd=None
        )

        self.add_parameter(
            name="voltage_ac", set_cmd=self._set_voltage_ac, get_cmd=None
        )

        self.add_parameter(
            name="frequency", set_cmd=self._set_frequency, get_cmd=None
        )

        self.add_parameter(name="capacitance",
                           get_cmd=self._get_capacitance,
                           snapshot_value=False)

        self.add_submodule('correction', Correction(self, 'correction'))

        self.add_parameter(name="phase_compensation_mode",
                           set_cmd=self._set_phase_compensation_mode,
                           get_cmd=None,
                           set_parser=constants.ADJ.Mode,
                           docstring=textwrap.dedent("""
            This parameter selects the MFCMU phase compensation mode. This
            command initializes the MFCMU. The available modes are captured 
            in :class:`constants.ADJ.Mode`:
 
                - 0: Auto mode. Initial setting.
                - 1: Manual mode.
                - 2: Load adaptive mode.
    
            For mode=0, the KeysightB1500 sets the compensation data 
            automatically. For mode=1, execute the 
            :meth:`phase_compensation` method (the ``ADJ?`` command) to
            perform the phase compensation and set the compensation data. 
            For mode=2, the KeysightB1500 performs the phase compensation 
            before every measurement. It is useful when there are wide load 
            fluctuations by changing the bias and so on."""))

        self._adc_mode = constants.ACT.Mode.PLC
        self._adc_coeff = 1
        self.add_parameter(name='adc_mode', 
                          set_cmd=self._set_adc_mode, 
                          get_cmd=None)

        self.add_parameter(name='adc_coeff',
                           set_cmd=self._set_adc_coeff,
                           get_cmd=None)
        
        self._sweep_auto_abort = True
        self._post_sweep_voltage_val = constants.WMDCV.Post.START
        self.add_parameter(name='sweep_auto_abort',
                           set_cmd=self._set_sweep_auto_abort,
                           get_cmd=None)

        self.add_parameter(name='post_sweep_voltage_val',
                           set_cmd=self._set_post_sweep_voltage_val,
                           get_cmd=None)

        self._sweep_hold_delay = 0
        self._sweep_delay = 0
        self._sweep_step_delay = 0
        self._sweep_trigger_delay = 0
        self._sweep_measure_delay = 0
        
        self.add_parameter(name='sweep_hold_delay',
                           set_cmd=self._set_sweep_hold_delay,
                           get_cmd=None)
        
        self.add_parameter(name='sweep_delay',
                           set_cmd=self._set_sweep_delay,
                           get_cmd=None)

        self.add_parameter(name='sweep_step_delay',
                           set_cmd=self._set_sweep_step_delay,
                           get_cmd=None)

        self.add_parameter(name='sweep_trigger_delay',
                           set_cmd=self._set_sweep_trigger_delay,
                           get_cmd=None)

        self.add_parameter(name='sweep_measure_delay',
                           set_cmd=self._set_sweep_measure_delay,
                           get_cmd=None)

        self._sweep_mode = constants.SweepMode.LINEAR
        self._sweep_start = 0
        self._sweep_end = 0
        self._sweep_steps = 1
        self.add_parameter(name='sweep_mode',
                           set_cmd=self._set_sweep_mode,
                           get_cmd=None)

        self.add_parameter(name='sweep_start',
                           set_cmd=self._set_sweep_start,
                           get_cmd=None,
                           unit='V')

        self.add_parameter(name='sweep_end',
                           set_cmd=self._set_sweep_end,
                           get_cmd=None,
                           unit='V')

        self.add_parameter(name='sweep_steps',
                           set_cmd=self._set_sweep_steps,
                           get_cmd=None)

        self.add_parameter(
            name="measurement_mode",
            get_cmd=None,
            set_cmd=self._set_measurement_mode,
            set_parser=MM.Mode,
            vals=vals.Enum(*list(MM.Mode)),
            docstring=textwrap.dedent("""
                Set measurement mode for this module.
                
                It is recommended for this parameter to use values from 
                :class:`.constants.MM.Mode` enumeration.
                
                Refer to the documentation of ``MM`` command in the 
                programming guide for more information.""")
        )

        self.add_parameter(name='impedance_model',
                           set_cmd=self._set_impedance_model,
                           get_cmd=None,
                           initial_value=constants.IMP.MeasurementMode.Cp_D)

        self.add_parameter(name='ac_dc_volt_monitor',
                           set_cmd=self._set_ac_dc_volt_monitor,
                           get_cmd=None,
                           initial_value=False)

        self._ranging_mode = constants.RangingMode.AUTO
        self._measurement_range_for_non_auto =  None
        self.add_parameter(name='ranging_mode',
                           set_cmd=self._set_ranging_mode,
                           get_cmd=None)
        
        self.add_parameter(name='measurement_range_for_non_auto',
                           set_cmd=self._set_measurement_range_for_non_auto,
                           get_cmd=None)
        
    def _set_voltage_dc(self, value: float) -> None:
        msg = MessageBuilder().dcv(self.channels[0], value)

        self.write(msg.message)

    def _set_voltage_ac(self, value: float) -> None:
        msg = MessageBuilder().acv(self.channels[0], value)

        self.write(msg.message)

    def _set_frequency(self, value: float) -> None:
        msg = MessageBuilder().fc(self.channels[0], value)

        self.write(msg.message)

    def _get_capacitance(self) -> Tuple[float, float]:
        self._set_measurement_mode(constants.MM.Mode.SPOT_C)
        
        msg = MessageBuilder().tc(
            chnum=self.channels[0], mode=constants.RangingMode.AUTO
        )

        response = self.ask(msg.message)

        parsed = [item for item in re.finditer(_pattern, response)]

        if (
                len(parsed) != 2
                or parsed[0]["dtype"] != "C"
                or parsed[1]["dtype"] != "Y"
        ):
            raise ValueError("Result format not supported.")

        return float(parsed[0]["value"]), float(parsed[1]["value"])

    def _set_phase_compensation_mode(self, mode: constants.ADJ.Mode) -> None:
        msg = MessageBuilder().adj(chnum=self.channels[0], mode=mode)
        self.write(msg.message)

    def phase_compensation(
            self,
            mode: Optional[Union[constants.ADJQuery.Mode, int]] = None
    ) -> constants.ADJQuery.Response:
        """
        Performs the MFCMU phase compensation, sets the compensation
        data to the KeysightB1500, and returns the execution results.

        This method resets the MFCMU. Before executing this method, set the
        phase compensation mode to manual by using
        ``phase_compensation_mode`` parameter, and open the measurement
        terminals at the end of the device side. The execution of this
        method will take about 30 seconds (the visa timeout for it is
        controlled by :attr:`phase_compensation_timeout` attribute). The
        compensation data is cleared by turning the KeysightB1500 off.

        Args:
            mode: Command operation mode :class:`.constants.ADJQuery.Mode`.

                - 0: Use the last phase compensation data without measurement.
                - 1: Perform the phase compensation data measurement.

                If the mode parameter is not set, mode=1 is assumed by the
                instrument.

        Returns:
            Status result of performing the phase compensation as
            :class:`.constants.ADJQuery.Response`
        """
        with self.root_instrument.timeout.set_to(
                self.phase_compensation_timeout):
            msg = MessageBuilder().adj_query(chnum=self.channels[0],
                                             mode=mode)
            response = self.ask(msg.message)
        return constants.ADJQuery.Response(int(response))

    def abort(self):
        """
        Aborts currently running operation and the subsequent execution.
        This does not abort the timeout process. Only when the kernel is
        free this command is executed and the further commands are aborted.
        """
        msg = MessageBuilder().ab()
        self.write(msg.message)

    def _set_adc_mode(self, adc_mode):
        self._adc_mode = adc_mode
        msg = MessageBuilder().act(mode = self._adc_mode, coeff=self._adc_coeff.message)
        self.write(msg)

    def _set_adc_coeff(self, adc_coeff):
        self._adc_coeff = adc_coeff
        msg = MessageBuilder().act(mode = self._adc_mode, coeff=self._adc_coeff).message
        self.write(msg)

    def _set_sweep_auto_abort(self, val):
        self._sweep_auto_abort = val
        msg = MessageBuilder().wmdcv(abort=self._sweep_auto_abort, post=self._sweep_auto_abort_post_val)
        self.write(msg.message)

    def _set_post_sweep_voltage_val(self, val):
        self._post_sweep_voltage_val = val
        msg = MessageBuilder().wmdcv(abort=self._sweep_auto_abort, post=self._sweep_auto_abort_post_val)
        self.write(msg.message)

    def _set_sweep_hold_delay(self, val):
        self._sweep_hold_delay = val
        msg = MessageBuilder().wtdcv(hold=self._sweep_hold_delay, 
                                     delay=self._sweep_delay, 
                                     step_delay=self._sweep_step_delay, 
                                     trigger_delay=self._sweep_trigger_delay, 
                                     measure_delay=self._sweep_measure_delay)
        self.write(msg.message)

    def _set_sweep_delay(self, val):
        self._sweep_delay = val
        msg = MessageBuilder().wtdcv(hold=self._sweep_hold_delay, 
                                     delay=self._sweep_delay, 
                                     step_delay=self._sweep_step_delay, 
                                     trigger_delay=self._sweep_trigger_delay, 
                                     measure_delay=self._sweep_measure_delay)
        self.write(msg.message)

    def _set_sweep_step_delay(self, val):
        self._sweep_step_delay = val
        msg = MessageBuilder().wtdcv(hold=self._sweep_hold_delay, 
                                     delay=self._sweep_delay, 
                                     step_delay=self._sweep_step_delay, 
                                     trigger_delay=self._sweep_trigger_delay, 
                                     measure_delay=self._sweep_measure_delay)
        self.write(msg.message)

    def _set_sweep_trigger_delay(self, val):
        self._sweep_sweep_trigger_delay = val
        msg = MessageBuilder().wtdcv(hold=self._sweep_hold_delay, 
                                     delay=self._sweep_delay, 
                                     step_delay=self._sweep_step_delay, 
                                     trigger_delay=self._sweep_trigger_delay, 
                                     measure_delay=self._sweep_measure_delay)
        self.write(msg.message)

    def _set_sweep_measure_delay(self, val):
        self._sweep_sweep_measure_delay = val
        msg = MessageBuilder().wtdcv(hold=self._sweep_hold_delay, 
                                     delay=self._sweep_delay, 
                                     step_delay=self._sweep_step_delay, 
                                     trigger_delay=self._sweep_trigger_delay, 
                                     measure_delay=self._sweep_measure_delay)
        self.write(msg.message)

    def _set_sweep_mode(self, val):
        self._sweep_mode = val
        msg = MessageBuilder().wdcv(chnum=self.channels[0], 
                                    mode=self._sweep_mode, 
                                    start=self._sweep_start, 
                                    stop=self._sweep_end, 
                                    step=self._sweep_steps)
        self.write(msg.message)

    def _set_sweep_start(self, val):
        self._sweep_start = val
        msg = MessageBuilder().wdcv(chnum=self.channels[0], 
                                    mode=self._sweep_mode, 
                                    start=self._sweep_start, 
                                    stop=self._sweep_end, 
                                    step=self._sweep_steps)
        self.write(msg.message)

    def _set_sweep_end(self, val):
        self._sweep_end = val
        msg = MessageBuilder().wdcv(chnum=self.channels[0], 
                                    mode=self._sweep_mode, 
                                    start=self._sweep_start, 
                                    stop=self._sweep_end, 
                                    step=self._sweep_steps)
        self.write(msg.message)

    def _set_sweep_steps(self, val):
        self._sweep_steps = val
        msg = MessageBuilder().wdcv(chnum=self.channels[0], 
                                    mode=self._sweep_mode, 
                                    start=self._sweep_start, 
                                    stop=self._sweep_end, 
                                    step=self._sweep_steps)
        self.write(msg.message)
    
    def _set_measurement_mode(self, mode: Union[MM.Mode, int]) -> None:
        self.write(MessageBuilder()
                   .mm(mode=mode,
                       channels=[self.channels[0]])
                   .message)

    def _set_impedance_model(self, val):
        msg = MessageBuilder().imp(mode = val)
        self.write(msg.message)

    def _set_ac_dc_volt_monitor(self, val):
        msg = MessageBuilder().lmn(enable_data_monitor=val).message
        self.write(msg)

    def _set_ranging_mode(self, val):
        self._ranging_mode = val
        if val == constants.RangingMode.AUTO:
            self._measurement_range_for_non_auto = None
        msg = MessageBuilder().rc(chnum=self.channels[0], 
                                  ranging_mode=self._ranging_mode, 
                                  measurement_range=self._measurement_range_for_non_auto)
        self.write(msg.message)

    def _set_measurement_range_for_non_auto(self, val):
        self._measurement_range_for_non_auto = val
        msg = MessageBuilder().rc(chnum=self.channels[0], 
                                  ranging_mode=self._ranging_mode, 
                                  measurement_range=self._measurement_range_for_non_auto)
        self.write(msg.message)

    def _setup_staircase_CV(
        self,
        v_start: float,
        v_end: float,
        N_steps: int,
        freq: float,
        AC_rms: float,
        hold_val_at_end: int = constants.WMDCV.Post.STOP,
        adc_mode:int = constants.ACT.Mode.PLC,
        adc_coeff: int = 5,
        imp_model: int = constants.IMP.MeasurementMode.Cp_D,
        ranging_mode: int = constants.RangingMode.AUTO,
        fixed_range_val: int = None,
        hold_delay: float = 0, 
        delay: float = 0, 
        step_delay: float = 0, 
        trigger_delay: float = 0,
        measure_delay: float = 0,
        abort_enabled: bool = constants.Abort.ENABLED,
        abort_post_val: int = constants.WMDCV.Post.START,
        sweep_mode: int = constants.SweepMode.LINEAR,
        volt_mon: bool = False
)->float:
        """
        Convenience function which requires all inputs to properly setup a CV sweep
        measurement.  Function sets parameters in the order given in the programming
        example in the manual.  Returns error status after setting all params.
        """
        
        #Set whether to return timestamp
        # msg = MessageBuilder().tsc(False).message
        # spa.write(msg)
        
        #cmu enable
        msg = MessageBuilder().cn(channels = self.channels).message
        self.write(msg)

        self.adc_mode(adc_mode)
        self.adc_coeff(adc_coeff)
        self.frequency(freq)
        self.voltage_ac(AC_rms)
        self.sweep_auto_abort(abort_enabled)
        self.post_sweep_voltage_val(abort_post_val)
        self.sweep_hold_delay(hold_delay)
        self.sweep_delay(delay)
        self.sweep_step_delay(step_delay)
        self.sweep_trigger_delay(trigger_delay)
        self.sweep_measure_delay(measure_delay)
        self.sweep_mode(sweep_mode)
        self.sweep_start(v_start)
        self.sweep_end(v_end)
        self.sweep_steps(N_steps)
        self.measurement_mode(constants.MM.Mode.CV_DC_SWEEP)
        self.impedance_model(imp_model)
        self.ac_dc_volt_monitor(volt_mon)
        self.ranging_mode(ranging_mode)
        self.measurement_range_for_non_auto(fixed_range_val)

        #Get error status
        msg = MessageBuilder().errx_query().message
        err = self.ask(msg)

        return err

def run_sweep(self):
    msg = MessageBuilder().xe().message
    raw_data = self.ask(msg)
    return raw_data


class Correction(InstrumentChannel):
    """
    A Keysight B1520A CMU submodule for performing open/short/load corrections.
    """

    def __init__(self, parent: 'B1520A', name: str, **kwargs):
        super().__init__(parent=parent, name=name, **kwargs)
        self._chnum = parent.channels[0]

        self.add_submodule('frequency_list',
                           FrequencyList(self, 'frequency_list', self._chnum))

    def enable(self, corr: constants.CalibrationType) -> None:
        """
        This command enables the open/short/load correction. Before enabling a
        correction, perform the corresponding correction data measurement by
        using the :meth:`perform`.

        Args:
            corr: Depending on the the correction you want to perform,
                set this to OPEN, SHORT or LOAD. For ex: In case of open
                correction corr = constants.CalibrationType.OPEN.
        """
        msg = MessageBuilder().corrst(chnum=self._chnum,
                                      corr=corr,
                                      state=True)
        self.write(msg.message)

    def disable(self, corr: constants.CalibrationType) -> None:
        """
        This command disables an open/short/load correction.

        Args:
            corr: Correction type as in :class:`.constants.CalibrationType`
        """
        msg = MessageBuilder().corrst(chnum=self._chnum,
                                      corr=corr,
                                      state=False)
        self.write(msg.message)

    def is_enabled(self, corr: constants.CalibrationType
                   ) -> constants.CORRST.Response:
        """
        Query instrument to see if a correction of the given type is
        enabled.

        Args:
            corr: Correction type as in :class:`.constants.CalibrationType`
        """
        msg = MessageBuilder().corrst_query(chnum=self._chnum, corr=corr)

        response = self.ask(msg.message)
        return constants.CORRST.Response(int(response))

    def set_reference_values(self,
                             corr: constants.CalibrationType,
                             mode: constants.DCORR.Mode,
                             primary: float,
                             secondary: float) -> None:
        """
        This command disables the open/short/load correction function and
        defines the calibration value or the reference value of the
        open/short/load standard. Any previously measured correction data
        will be invalid after calling this method.

        Args:
            corr: Correction mode from :class:`.constants.CalibrationType`.
                OPEN for Open correction
                SHORT for Short correction
                LOAD for Load correction.
            mode:  Measurement mode from :class:`.constants.DCORR.Mode`
                Cp-G (for open correction)
                Ls-Rs (for short or load correction).
            primary: Primary reference value of the standard. Cp value for
                the open standard. in F. Ls value for the short or load
                standard. in H.
            secondary: Secondary reference value of the standard. G value
                for the open standard. in S. Rs value for the short or load
                standard. in Ω.
        """

        msg = MessageBuilder().dcorr(chnum=self._chnum,
                                     corr=corr,
                                     mode=mode,
                                     primary=primary,
                                     secondary=secondary)
        self.write(msg.message)

    def get_reference_values(self, corr: constants.CalibrationType) -> str:
        """
        This command returns the calibration values or the reference values of
        the open/short/load standard.

        Args:
            corr: Correction mode from :class:`.constants.CalibrationType`.
                OPEN for Open correction
                SHORT for Short correction
                LOAD for Load correction.

        Returns:
            A human-readable string with the correction mode
            :class:`.constants.DCORR.Mode` and its reference values
        """
        dcorr_response_tuple = self._get_reference_values(corr=corr)
        return format_dcorr_response(dcorr_response_tuple)

    def _get_reference_values(self, corr: constants.CalibrationType
                              ) -> _DCORRResponse:
        msg = MessageBuilder().dcorr_query(chnum=self._chnum, corr=corr)
        response = self.ask(msg.message)
        return parse_dcorr_query_response(response)

    def perform(self, corr: constants.CalibrationType
                ) -> constants.CORR.Response:
        """
        Perform Open/Short/Load corrections using this method. Refer to the
        example notebook to understand how each of the corrections are
        performed.

        Before executing this method, set the oscillator level of the MFCMU.

        If you use the correction standard, execute the
        :meth:`set_reference_values` method (corresponds to the ``DCORR``
        command) before this method because the calibration value or the
        reference value of the standard must be defined before performing
        the correction.

        Args:
            corr: Depending on the the correction you want to perform,
                set this to OPEN, SHORT or LOAD. For ex: In case of open
                correction corr = constants.CalibrationType.OPEN.

        Returns:
            Status of correction data measurement in the form of
            :class:`.constants.CORR.Response`
        """
        msg = MessageBuilder().corr_query(
            chnum=self._chnum,
            corr=corr
        )
        response = self.ask(msg.message)
        return constants.CORR.Response(int(response))

    def perform_and_enable(self, corr: constants.CalibrationType) -> str:
        """
        Perform the correction AND enable it. It is equivalent to calling
        :meth:`perform` and :meth:`enable` methods sequentially.

        Returns:
            A human readable string with status of the operation.
        """
        correction_status = self.perform(corr=corr)
        self.enable(corr=corr)

        is_enabled = self.is_enabled(corr=corr)
        response_out = f'Correction status {correction_status.name} and Enable' \
                       f' {is_enabled.name}'
        return response_out


class FrequencyList(InstrumentChannel):
    """
    A frequency list for open/short/load correction for Keysight B1520A CMU.
    """

    def __init__(self, parent: 'Correction', name: str, chnum: int, **kwargs):
        super().__init__(parent=parent, name=name, **kwargs)
        self._chnum = chnum

    def clear(self) -> None:
        """
        Remove all frequencies in the list for data correction.
        """
        self._clear(constants.CLCORR.Mode.CLEAR_ONLY)

    def clear_and_set_default(self) -> None:
        """
        Remove all frequencies in the list for data correction AND set the
        default frequency list.

        For the list of default frequencies, refer to the documentation of
        the ``CLCORR`` command in the programming manual.
        """
        self._clear(constants.CLCORR.Mode.CLEAR_AND_SET_DEFAULT_FREQ)

    def _clear(self, mode: constants.CLCORR.Mode) -> None:
        msg = MessageBuilder().clcorr(chnum=self._chnum, mode=mode)
        self.write(msg.message)

    def add(self, freq: float) -> None:
        """
        Append MFCMU output frequency for data correction in the list.

        The frequency value can be given with a certain resolution as per
        Table 4-18 in the programming manual (year 2016).
        """
        msg = MessageBuilder().corrl(chnum=self._chnum, freq=freq)
        self.write(msg.message)

    def query(self, index: Optional[int] = None) -> float:
        """
        Query the frequency list for CMU data correction.

        If ``index`` is ``None``, the query returns a total number of
        frequencies in the list. If ``index`` is given, then the query
        returns the frequency value from the list at that index.
        """
        msg = MessageBuilder().corrl_query(chnum=self._chnum,
                                           index=index)
        response = self.ask(msg.message)
        return float(response)
