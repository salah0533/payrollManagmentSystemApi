
class AppException(Exception):
    def __int__(self,message:str):
        super().__init__(message)