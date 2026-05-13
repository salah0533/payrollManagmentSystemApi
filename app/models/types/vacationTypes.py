from enum import IntEnum



class VacationTypes(IntEnum):
    paid = 0
    unpaid = 1
    sick = 2
    emergency = 3

    yearly_vacation = 0
    sick_leave = 2
    vacation = 0


    # {
    #   "id": 0,
    #   "vacation_type": "yearly_vacation"
    # },
    # {
    #   "id": 1,
    #   "vacation_type": "sick_leave"
    # },
    # {
    #   "id": 2,
    #   "vacation_type": "vacation"
    # }
