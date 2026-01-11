from fastapi import APIRouter

router = APIRouter()

@router.get("/{id}")
def get_employee(id:int):

