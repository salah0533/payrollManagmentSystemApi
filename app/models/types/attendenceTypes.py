from enum import IntEnum



class AttendanceType(IntEnum):
    Presnt = 0
    LATE = 1
    Absent=2
    OVERTIME = 3
    PAID_VACATION = 4
    Not_PAID_VACATION = 5
    Sick_Leave = 6