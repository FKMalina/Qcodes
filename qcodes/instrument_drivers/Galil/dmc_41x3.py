"""
This file holds the QCoDeS driver for the Galil DMC-41x3 motor controllers,
colloquially known as the "stepper motors".
"""
from typing import Any, Dict, Optional, List, Tuple
import numpy as np

from qcodes.instrument.base import Instrument
from qcodes.instrument.channel import InstrumentChannel
from qcodes.utils.validators import Enum, Ints, Union

try:
    import gclib
except ImportError as e:
    raise ImportError(
        "Cannot find gclib library. Download gclib installer from "
        "https://www.galil.com/sw/pub/all/rn/gclib.html and install Galil "
        "motion controller software for your OS. Afterwards go "
        "to https://www.galil.com/sw/pub/all/doc/gclib/html/python.html and "
        "follow instruction to be able to import gclib package in your "
        "environment.") from e


class GalilMotionController(Instrument):
    """
    Base class for Galil Motion Controller drivers
    """
    def __init__(self, name: str, address: str, **kwargs: Any) -> None:
        super().__init__(name=name, **kwargs)
        self.g = gclib.py()
        self.address = address
        self.open()

    def open(self) -> None:
        """
        Open connection to Galil motion controller. This method assumes that
        the initial mapping of Galil motion controller's hardware's mapping
        to an IP address is done using GDK and the IP address in burned in.
        This applies that Motion controller no more requests for an IP address
        and a connection to the Motion controller can be done by the IP
        address burned in.
        """
        self.g.GOpen(self.address + ' --direct -s ALL')

    def get_idn(self) -> Dict[str, Optional[str]]:
        """
        Get Galil motion controller hardware information
        """
        data = self.g.GInfo().split(" ")
        idparts: List[Optional[str]] = ["Galil Motion Control, Inc.",
                                        data[1], data[4], data[3][:-1]]

        return dict(zip(('vendor', 'model', 'serial', 'firmware'), idparts))

    def write_raw(self, cmd: str) -> None:
        """
        Write for Galil motion controller
        """
        self.g.GCommand(cmd+"\r")

    def ask_raw(self, cmd: str) -> str:
        """
        Asks/Reads data from Galil motion controller
        """
        return self.g.GCommand(cmd+"\r")

    def timeout(self, val: int) -> None:
        """
        Sets timeout for the instrument

        Args:
            val: time in milliseconds
        """
        if val < 1:
            raise RuntimeError("Timeout can not be less than 1 ms")

        self.g.GTimeout(val)

    def close(self) -> None:
        """
        Close connection to the instrument
        """
        self.g.GClose()

    def motion_complete(self, axes: str) -> None:
        """
        Wait for motion to complete for given axes
        """
        self.g.GMotionComplete(axes)


class VectorMode(InstrumentChannel):
    """
    Class to control motors in vector mode
    """

    def __init__(self,
                 parent: "DMC4133Controller",
                 name: str,
                 **kwargs: Any) -> None:
        super().__init__(parent, name, **kwargs)
        self._plane = name

        self.add_parameter("coordinate_system",
                           get_cmd="CA ?",
                           get_parser=self._parse_coordinate_system_active,
                           set_cmd="CA {}",
                           vals=Enum("S", "T"),
                           docstring="sets coordinate system for the motion")

        self.add_parameter("clear_sequence",
                           get_cmd=None,
                           set_cmd="CS {}",
                           vals=Enum("S", "T"),
                           docstring="clears vectors specified in the given "
                                     "coordinate system")

        self.add_parameter("vector_acceleration",
                           get_cmd="VA ?",
                           get_parser=int,
                           set_cmd="VA {}",
                           vals=Ints(1024, 1073740800),
                           unit="counts/sec2",
                           docstring="sets and gets the defined vector's "
                                     "acceleration")

        self.add_parameter("vector_deceleration",
                           get_cmd="VD ?",
                           get_parser=int,
                           set_cmd="VD {}",
                           vals=Ints(1024, 1073740800),
                           unit="counts/sec2",
                           docstring="sets and gets the defined vector's "
                                     "deceleration")

        self.add_parameter("vector_speed",
                           get_cmd="VS ?",
                           get_parser=int,
                           set_cmd="VS {}",
                           vals=Ints(2, 15000000),
                           unit="counts/sec",
                           docstring="sets and gets defined vector's speed")

    @staticmethod
    def _parse_coordinate_system_active(val: str) -> str:
        """
        parses the the current active coordinate system
        """
        if int(val):
            return "T"
        else:
            return "S"

    def activate(self) -> None:
        """
        activate plane of motion
        """
        self.write(f"VM {self._plane}")

    def vector_position(self, first_coord: int, second_coord: int) -> None:
        """
        sets the final vector position for the motion considering current position as the origin
        """
        self.write(f"VP {first_coord},{second_coord}")

    def vector_seq_end(self) -> None:
        """
        indicates to the controller that the end of the vector is coming up.
        is required to exit the vector mode gracefully
        """
        self.write("VE")

    def begin_seq(self) -> None:
        """
        begins motion of the motor
        """
        self.write("BG S")

    def after_seq_motion(self) -> None:
        """
        wait till motion ends
        """
        self.write("AM S")


class Motor(InstrumentChannel):
    """
    Class to control motors independently
    """

    def __init__(self,
                 parent: "DMC4133Controller",
                 name: str,
                 **kwargs: Any) -> None:
        super().__init__(parent, name, **kwargs)
        self._axis = name

        self.add_parameter("relative_position",
                           unit="quadrature counts",
                           get_cmd=f"MG _PR{self._axis}",
                           get_parser=float,
                           set_cmd=self._set_relative_position,
                           vals=Ints(-2147483648, 2147483647),
                           docstring="sets relative position for the motor's "
                                     "move")

        self.add_parameter("speed",
                           unit="counts/sec",
                           get_cmd=f"MG _SP{self._axis}",
                           get_parser=float,
                           set_cmd=self._set_speed,
                           vals=Ints(0, 3000000),
                           docstring="speed for motor's motion")

        self.add_parameter("acceleration",
                           unit="counts/sec2",
                           get_cmd=f"MG _AC{self._axis}",
                           get_parser=float,
                           set_cmd=self._set_acceleration,
                           vals=Ints(1024, 1073740800),
                           docstring="acceleration for motor's motion")

        self.add_parameter("deceleration",
                           unit="counts/sec2",
                           get_cmd=f"MG _DC{self._axis}",
                           get_parser=float,
                           set_cmd=self._set_deceleration,
                           vals=Ints(1024, 1073740800),
                           docstring="deceleration for motor's motion")

        self.add_parameter("homing_velocity",
                           unit="counts/sec",
                           get_cmd=f"MG _HV{self._axis}",
                           get_parser=float,
                           set_cmd=self._set_homing_velocity,
                           vals=Ints(0, 3000000),
                           docstring="sets the slew speed for the FI "
                                     "final move to the index and all but the "
                                     "first stage of HM (home)")

        self.add_parameter("off_when_error_occurs",
                           get_cmd=self._get_off_when_error_occurs,
                           set_cmd=self._set_off_when_error_occurs,
                           val_mapping={"disable": 0,
                                        "enable for position, amplifier error or "
                                        "abort input": 1,
                                        "enable for hardware limit switch": 2,
                                        "enable for all": 3},
                           docstring="enables or disables the motor to "
                                     "automatically turn off when error occurs")

        self.add_parameter(
            "enable_stepper_position_maintenance_mode",
            get_cmd=None,
            set_cmd=self._enable_disable_spm_mode,
            val_mapping={"enable": 1,
                         "disable": 0},
            docstring="enables, disables and gives status of error in SPM mode")

    def _get_off_when_error_occurs(self) -> int:
        """Gets the status if motor is automatically set to turn off when error occurs."""

        val = self.ask(f"MG _OE{self._axis}")

        return int(val[0])

    def _enable_disable_spm_mode(self, val: int) -> None:
        """
        enables/disables Stepper Position Maintenance mode and allows for error
        correction when error happens
        """
        if val:
            self.off_when_error_occurs("enable for position, amplifier error "
                                       "or abort input")
            self._setup_spm()
            self.servo_here()  # Enable axis
            self.write(f"YS{self._axis}={val}")
        else:
            self.write(f"YS{self._axis}={val}")
            self.off_when_error_occurs("disable")
            self.off()

    def stepper_position_maintenance_mode_status(self) -> str:
        """
        gives the status if the motor is in SPM mode enabled, disabled or an
        error has occurred. if error has occurred status is received,
        then error can be cleared by enabling
        `enable_stepper_position_maintenance_mode`.
        """
        val = self.ask(f"MG _YS{self._axis}")
        if val[0] == "0":
            return "SPM mode disabled"
        elif val[0] == "1":
            return "SPM mode enabled and no error has occurred"
        else:
            return "Error Occurred"

    def _set_off_when_error_occurs(self, val: int) -> None:
        """
        sets the motor to turn off automatically when the error occurs
        """
        self.write(f"OE{self._axis}={val}")

    def _set_homing_velocity(self, val: str) -> None:
        """
        sets the slew speed for the FI final move to the index and all but
        the first stage of HM.
        """
        self.write(f"HV{self._axis}={val}")

    def _set_deceleration(self, val: str) -> None:
        """
        set deceleration for the motor's motion
        """
        self.write(f"DC{self._axis}={val}")

    def _set_acceleration(self, val: str) -> None:
        """
        set acceleration for the motor's motion
        """
        self.write(f"AC{self._axis}={val}")

    def _set_speed(self, val: str) -> None:
        """
        sets speed for motor's motion
        """
        self.write(f"SP{self._axis}={val}")

    def _set_relative_position(self, val: str) -> None:
        """
        sets relative position
        """
        self.write(f"PR{self._axis}={val}")

    def _setup_spm(self) -> None:
        """
        sets up for Stepper Position Maintenance (SPM) mode
        """
        # Set the profiler to stop axis upon error
        self.write(f"KS{self._axis}=16")  # Set step smoothing
        self.write(f"MT{self._axis}=-2")  # Motor type set to stepper
        self.write(f"YA{self._axis}=64")   # Step resolution of the drive

        # Motor resolution (full steps per revolution)
        self.write(f"YB{self._axis}=200")
        # Encoder resolution (counts per revolution)
        self.write(f"YC{self._axis}=4000")

    def off(self) -> None:
        """
        turns motor off
        """
        self.write(f"MO {self._axis}")

    def on_off_status(self) -> str:
        """
        tells motor on off status
        """
        val = self.ask(f"MG _MO{self._axis}")
        if val[0] == "1":
            return "off"
        else:
            return "on"

    def servo_here(self) -> None:
        """
        servo at the motor
        """
        self.write(f"SH {self._axis}")

    def begin(self) -> None:
        """
        begins motion of the motor and waits until motor stops moving
        """
        self.write(f"BG {self._axis}")

        while int(float(self.ask(f"MG _BG{self._axis}"))):
            pass

    def home(self) -> None:
        """
        performs a three stage homing sequence for servo systems and a two
        stage sequence for stepper motor.

         Step One. Servos and Steppers
            - During the first stage of the homing sequence, the motor moves at
            the user-programmed speed until detecting a transition on the
            homing input for that axis. The speed for step one is set with the
            SP command.

            - The direction for this first stage is determined by the
            initial state of the homing input. The state of the homing input
            can be configured using the second field of the CN command.

            - Once the homing input changes state, the motor decelerates to a
            stop.

        Step Two. Servos and Steppers
            - At the second stage, the motor changes directions and
            approaches the transition again at the speed set with the
            HV command. When the transition is detected, the motor is stopped
            instantaneously.

        Step Three. Servos only
            - At the third stage, the motor moves in the positive direction
            at the speed set with the HV command until it detects an index
            pulse via latch from the encoder. It returns to the latched
            position and defines it as position 0.
        """
        # setup for homing
        self.speed(2000)
        self.homing_velocity(256)

        # home command
        self.write(f"HM {self._axis}")

        self.servo_here()

        # begin motion
        self.begin()

    def error_magnitude(self) -> float:
        """
        gives the magnitude of error, in drive step counts, for axes in
        Stepper Position Maintenance mode.

        a step count is directly proportional to the micro-stepping
        resolution of the stepper drive.
        """
        return float(self.ask(f"QS{self._axis}=?"))

    def correct_error(self) -> None:
        """
        this allows the user to correct for position error in Stepper Position
        Maintenance mode and after correction sets
        `stepper_position_maintenance_mode_status` back to enable
        """
        self.write(f"YR{self._axis}=_QS{self._axis}")


class DMC4133Controller(GalilMotionController):
    """
    Driver for Galil DMC-4133 Controller
    """

    def __init__(self,
                 name: str,
                 address: str,
                 **kwargs: Any) -> None:
        super().__init__(name=name, address=address, **kwargs)

        self.add_parameter("position_format_decimals",
                           get_cmd=None,
                           set_cmd="PF 10.{}",
                           vals=Ints(0, 4),
                           docstring="sets number of decimals in the format "
                                     "of the position")

        self.add_parameter("absolute_position",
                           get_cmd=self._get_absolute_position,
                           set_cmd=None,
                           unit="quadrature counts",
                           docstring="gets absolute position of the motors "
                                     "from the set origin")

        self.add_parameter("wait",
                           get_cmd=None,
                           set_cmd="WT {}",
                           unit="ms",
                           vals=Ints(2, 2147483646),
                           docstring="controller will wait for the amount of "
                                     "time specified before executing the next "
                                     "command")

        self._set_default_update_time()
        self.add_submodule("motor_a", Motor(self, "A"))
        self.add_submodule("motor_b", Motor(self, "B"))
        self.add_submodule("motor_c", Motor(self, "C"))
        self.add_submodule("plane_ab", VectorMode(self, "AB"))
        self.add_submodule("plane_bc", VectorMode(self, "BC"))
        self.add_submodule("plane_ac", VectorMode(self, "AC"))

        self.connect_message()

    def _set_default_update_time(self) -> None:
        """
        sets sampling period to default value of 1000. sampling period affects
        the AC, AS, AT, DC, FA, FV, HV, JG, KP, NB, NF, NZ, PL, SD, SP, VA,
        VD, VS, WT commands.
        """
        self.write("TM 1000")

    def _get_absolute_position(self) -> Dict[str, int]:
        """
        gets absolution position of the motors from the defined origin
        """
        result = dict()
        data = self.ask("PA ?,?,?").split(" ")
        result["A"] = int(data[0][:-1])
        result["B"] = int(data[1][:-1])
        result["C"] = int(data[2])

        return result

    def end_program(self) -> None:
        """
        ends the program
        """
        self.write("EN")

    def define_position_as_origin(self) -> None:
        """
        defines current motors position as origin
        """
        self.write("DP 0,0,0")

    def tell_error(self) -> str:
        """
        reads error
        """
        return self.ask("TC1")

    def stop(self) -> None:
        """
        stop the motion of all motors
        """
        self.write("ST")

    def abort(self) -> None:
        """
        aborts motion and the program operation
        """
        self.write("AB")

    def motors_off(self) -> None:
        """
        turn all motors off
        """
        self.write("MO")

    def begin_motors(self) -> None:
        """
        begin motion of all motors simultaneously
        """
        self.write("BG")

        while int(float(self.ask("MG _BGA"))) or int(float(self.ask("MG _BGB"))) or int(float(self.ask("MG _BGC"))):
            pass


class Arm:
    """ Module to control probe arm"""
    def __init__(self,
                 controller: DMC4133Controller) -> None:

        self.controller = controller

        # initialization
        self.left_bottom_position: Tuple[int, int, int]
        self.left_top_position: Tuple[int, int, int]
        self.right_top_position: Tuple[int, int, int]

        # motion directions
        self._a: np.ndarray     # right_top - left_bottom
        self._b: np.ndarray     # left_top - left_bottom
        self._c: np.ndarray     # right_top - left_top
        self._n: np.ndarray
        self.norm_a: float
        self.norm_b: float
        self.norm_c: float

        self._plane_eqn: np.ndarray    # eqn of the chip plane

        # current vars
        self.current_row: Optional[int] = None
        self.current_pad: Optional[int] = None

        # chip details
        self.rows: int
        self.pads: int
        self.inter_row_dis: float
        self.inter_pad_dis: float

    def set_left_bottom_position(self) -> None:

        pos = self.controller.absolute_position()
        self.left_bottom_position = (pos["A"], pos["B"], pos["C"])

    def set_left_top_position(self) -> None:

        pos = self.controller.absolute_position()
        self.left_top_position = (pos["A"], pos["B"], pos["C"])


    def set_right_top_position(self) -> None:

        pos = self.controller.absolute_position()
        self.right_top_position = (pos["A"], pos["B"], pos["C"])

        self._calculate_ortho_vector()

    def _calculate_ortho_vector(self) -> None:

        a = np.array(tuple(map(lambda i, j: i - j, self.right_top_position, self.left_bottom_position)))
        self.norm_a = np.linalg.norm(a)
        self._a = a / self.norm_a

        b = np.array(tuple(map(lambda i, j: i - j, self.left_top_position, self.left_bottom_position)))
        self.norm_b = np.linalg.norm(b)
        self._b = b / self.norm_b

        c = np.array(tuple(map(lambda i, j: i - j, self.right_top_position, self.left_top_position)))
        self.norm_c = np.linalg.norm(c)
        self._c = c / self.norm_c

        n = np.cross(self._a, self._b)
        norm_n = np.linalg.norm(n)
        self._n = n / norm_n

        intercept = np.array(-1 * self._n * self.left_bottom_position)
        self._plane_eqn = np.append(self._n, intercept)

    def _setup_motion(self, rel_vec: np.ndarray, d: float, speed: float) -> None:

        pos = self.controller.absolute_position()

        a = int(np.round(rel_vec[0] * d))
        b = int(np.round(rel_vec[1] * d))
        c = int(np.round(rel_vec[2] * d))

        target = np.array(pos["A"] + a, pos["B"] + b, pos["C"] + c, 1)

        if np.dot(self._plane_eqn, target) < 0:
            raise RuntimeError(f"Cannot move to {target[:2]}. Target location is below chip plane.")

        sp_a = int(np.round(abs(rel_vec[0]) * speed))
        sp_b = int(np.round(abs(rel_vec[1]) * speed))
        sp_c = int(np.round(abs(rel_vec[2]) * speed))

        motorA = self.controller.motor_a
        motorB = self.controller.motor_b
        motorC = self.controller.motor_c

        motorA.relative_position(a)
        motorA.speed(sp_a)
        motorA.acceleration(50000)
        motorA.deceleration(50000)
        motorA.servo_here()

        motorB.relative_position(b)
        motorB.speed(sp_b)
        motorB.acceleration(50000)
        motorB.deceleration(50000)
        motorB.servo_here()

        motorC.relative_position(c)
        motorC.speed(sp_c)
        motorC.acceleration(50000)
        motorC.deceleration(50000)
        motorC.servo_here()

    def _move(self) -> None:
        self.controller.begin_motors()

    def _pick_up(self) -> None:

        self._setup_motion(rel_vec=self._n, d=60000, speed=3000)
        self._move()

    def _put_down(self) -> None:

        motion_vec = -1*self._n
        self._setup_motion(rel_vec=motion_vec, d=60000, speed=3000)
        self._move()

    def move_towards_left_bottom_position(self) -> None:

        self._pick_up()

        motion_vec = -1*self._a
        self._setup_motion(rel_vec=motion_vec, d=self.norm_a, speed=3000)
        self._move()
        self.current_row = 1
        self.current_pad = 1

        self._put_down()

    def move_to_next_row_pad(self) -> None:

        if self.current_row is None or self.current_pad is None:
            raise RuntimeError("Current position unknown.")

        if self.current_row == self.rows:
            raise RuntimeError("Cannot move further")

        self.current_row = self.current_row + 1

        self._setup_motion(rel_vec=self._b, d=self.inter_row_dis, speed=3000)
        self._move()

    def move_to_begin_row_pad(self) -> None:

        if self.current_row is None or self.current_pad is None:
            raise RuntimeError("Current position unknown.")

        if self.current_pad == self.pads:
            raise RuntimeError("Cannot move further")

        self.current_row = 1
        self.current_pad = self.current_pad + 1

        motion_vec = -1 * self._b * self.norm_b + self._c * self.inter_pad_dis
        norm = np.linalg.norm(motion_vec)
        motion_vec_cap = motion_vec / norm

        self._setup_motion(rel_vec=motion_vec_cap, d=norm, speed=3000)
        self._move()
