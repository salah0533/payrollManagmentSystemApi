from enum import IntEnum



class AttendanceType(IntEnum):
    Presnt = 1
    LATE = 2
    Absent=3
    OVERTIME = 4
    PAID_VACATION = 5
    Not_PAID_VACATION = 6
    Sick_Leave = 7