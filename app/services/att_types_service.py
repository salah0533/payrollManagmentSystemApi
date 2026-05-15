from app.utility.reference_codes import ATTENDANCE_STATUS_CODES


def get_att_types_srv(db):
    return [
        {"id": index, "code": code, "attendence_type": code}
        for index, code in enumerate(ATTENDANCE_STATUS_CODES)
    ]
