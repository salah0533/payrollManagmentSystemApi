# API Response and Error Handling

## Goals

- Keep the existing success response shape used by the frontend: `message`, `data`, `status`
- Standardize all error responses behind global exception handlers
- Return proper HTTP status codes for validation, authentication, authorization, conflicts, missing resources, database constraint failures, and unexpected server errors
- Avoid exposing stack traces, raw SQL errors, or sensitive internals to clients
- Centralize rollback and logging behavior so routes stay focused on business logic

## Standard Success Response

All successful endpoints now return the same envelope:

```json
{
  "message": "",
  "data": {},
  "status": true
}
```

Notes:

- `data` may be an object, array, scalar, or `null`
- create-style endpoints now use `201 Created` where it is safe to do so while keeping the same JSON envelope

## Standard Error Response

All handled failures now return this envelope:

```json
{
  "message": "Validation failed",
  "data": null,
  "status": false,
  "detail": "Validation failed",
  "error_code": "validation_error",
  "errors": [
    {
      "field": "year_month",
      "location": "body",
      "message": "Invalid format. Use YYYY-MM",
      "type": "value_error"
    }
  ]
}
```

Compatibility notes:

- `message`, `data`, and `status` are preserved for frontend compatibility
- `detail` is included for compatibility with clients that previously expected FastAPI-style error payloads
- `errors` is always present and is an empty array when there are no field-level errors

## Exception Sources

### Custom application exceptions

Use `AppException` subclasses for business failures:

- `BadRequestException`
- `UnauthorizedException`
- `ForbiddenException`
- `NotFoundException`
- `ConflictException`
- `ValidationException`
- `ResourceNotFoundException`

### Framework and database exceptions

Global handlers also normalize:

- `RequestValidationError`
- `HTTPException`
- `IntegrityError`
- `SQLAlchemyError`
- unexpected `Exception`

## Logging and Safety

- Unhandled server and database errors are logged on the server
- Request method and path are logged with the failure
- Stack traces are logged server-side only
- Client responses never include Python tracebacks or raw SQL exception text
- Database sessions now roll back automatically when a request raises an exception

## Migration Rules for New Endpoints

When adding or updating endpoints:

1. Return `api_success(...)` instead of handwritten success dictionaries
2. Raise custom application exceptions from services and dependencies for business-rule failures
3. Let the global handlers format the response
4. Avoid local `try/except` in routes unless you are translating a third-party error into a domain-specific exception

## Manual Test Cases

### 1. Validation error shape

Request:

```bash
curl -i -X PUT http://localhost:8000/payment/ ^
  -H "Content-Type: application/json" ^
  -d "{\"employee_id\":1,\"date\":\"2026-05-01\",\"payment_type\":1,\"amount\":10,\"description\":\"bonus\",\"year_month\":\"2026-13\"}"
```

Expected:

- HTTP `422`
- `status` is `false`
- `message` is `Validation failed`
- `errors[0].field` is `year_month`

### 2. Unauthorized access

Request:

```bash
curl -i http://localhost:8000/auth/me
```

Expected:

- HTTP `401`
- `error_code` is `unauthorized`
- no stack trace in the response

### 3. Missing resource

Request:

```bash
curl -i http://localhost:8000/employee/999999 \
  -H "Authorization: Bearer <token>"
```

Expected:

- HTTP `404`
- `status` is `false`
- `message` clearly states that the employee was not found

### 4. Conflict response

Request:

Submit a vacation request that overlaps an existing approved or pending vacation.

Expected:

- HTTP `409`
- `error_code` is `vacation_overlap`
- `status` is `false`

### 5. Success response consistency

Request:

```bash
curl -i http://localhost:8000/
```

Expected:

- HTTP `200`
- body contains only `message`, `data`, and `status`

## Automated Test Coverage

The automated contract tests live in `tests/test_response_handling.py`.

Run them with:

```bash
python -m unittest discover -s tests -v
```
