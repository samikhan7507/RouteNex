# API documentation
Interactive OpenAPI: `http://localhost:8000/docs`; schema: `/openapi.json`.

Main groups: `/api/auth/*`, `/api/items`, `/api/addresses`, `/api/orders`, `/api/rides`, `/api/vehicles`, `/api/drivers`, `/api/optimizer/run`, `/api/reroute`, `/api/routes`, `/api/alerts`, `/api/analytics/summary`, `/api/ml/predictions`, `/api/audit`.

Send `Authorization: Bearer <access_token>`. Login payload: `{"email":"samikhan@routenex.in","password":"Demo@123"}`. All errors use FastAPI's standard `{ "detail": "..." }` envelope.
