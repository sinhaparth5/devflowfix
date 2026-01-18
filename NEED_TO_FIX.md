    raise exc
  File "/home/appuser/.local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/appuser/.local/lib/python3.13/site-packages/fastapi/routing.py", line 101, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "/home/appuser/.local/lib/python3.13/site-packages/fastapi/routing.py", line 345, in app
    solved_result = await solve_dependencies(
                    ^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<6 lines>...
    )
    ^
  File "/home/appuser/.local/lib/python3.13/site-packages/fastapi/dependencies/utils.py", line 614, in solve_dependencies
    solved_result = await solve_dependencies(
                    ^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<9 lines>...
    )
    ^
  File "/home/appuser/.local/lib/python3.13/site-packages/fastapi/dependencies/utils.py", line 643, in solve_dependencies
    solved = await call(**solved_result.values)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/auth/zitadel.py", line 320, in get_current_user
    return await auth.get_user_from_token(credentials.credentials)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/auth/zitadel.py", line 281, in get_user_from_token
    claims = await self.validate_token(token)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/auth/zitadel.py", line 220, in validate_token
    signing_key = self._get_signing_key(token, jwks)
  File "/app/app/auth/zitadel.py", line 177, in _get_signing_key
    unverified_header = jwt.get_unverified_header(token)
  File "/home/appuser/.local/lib/python3.13/site-packages/jose/jwt.py", line 202, in get_unverified_header
    raise JWTError("Error decoding token headers.")
jose.exceptions.JWTError: Error decoding token headers.
2026-01-18T20:39:14.115330Z [error    ] unhandled_exception            [app.middleware] error='Error decoding token headers.' path=/api/v1/analytics/trends request_id=req_1768768753529660
Traceback (most recent call last):
  File "/home/appuser/.local/lib/python3.13/site-packages/jose/jws.py", line 180, in _load
    signing_input, crypto_segment = jwt.rsplit(b".", 1)
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
ValueError: not enough values to unpack (expected 2, got 1)
During handling of the above exception, another exception occurred:
Traceback (most recent call last):
  File "/home/appuser/.local/lib/python3.13/site-packages/jose/jwt.py", line 200, in get_unverified_header
    headers = jws.get_unverified_headers(token)
  File "/home/appuser/.local/lib/python3.13/site-packages/jose/jws.py", line 113, in get_unverified_headers
    return get_unverified_header(token)
  File "/home/appuser/.local/lib/python3.13/site-packages/jose/jws.py", line 94, in get_unverified_header
    header, claims, signing_input, signature = _load(token)
                                               ~~~~~^^^^^^^
  File "/home/appuser/.local/lib/python3.13/site-packages/jose/jws.py", line 184, in _load
    raise JWSError("Not enough segments")
jose.exceptions.JWSError: Not enough segments
The above exception was the direct cause of the following exception:
Traceback (most recent call last):
  File "/home/appuser/.local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
  File "/app/app/middleware.py", line 150, in dispatch
    return await call_next(request)
    await app(scope, receive, sender)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/appuser/.local/lib/python3.13/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
  File "/home/appuser/.local/lib/python3.13/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
    await self.app(scope, receive, send)
  File "/home/appuser/.local/lib/python3.13/site-packages/starlette/middleware/base.py", line 144, in coro
  File "/home/appuser/.local/lib/python3.13/site-packages/starlette/routing.py", line 716, in __call__
    await self.app(scope, receive_or_disconnect, send_no_error)
    await self.middleware_stack(scope, receive, send)
  File "/home/appuser/.local/lib/python3.13/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "/home/appuser/.local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/appuser/.local/lib/python3.13/site-packages/fastapi/dependencies/utils.py", line 614, in solve_dependencies
    ...<6 lines>...
    )
  File "/home/appuser/.local/lib/python3.13/site-packages/starlette/routing.py", line 736, in app
    ^
    await route.handle(scope, receive, send)
  File "/home/appuser/.local/lib/python3.13/site-packages/starlette/routing.py", line 290, in handle
  File "/home/appuser/.local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    await self.app(scope, receive, send)
  File "/home/appuser/.local/lib/python3.13/site-packages/fastapi/routing.py", line 115, in app
    raise exc
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "/home/appuser/.local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/appuser/.local/lib/python3.13/site-packages/fastapi/routing.py", line 101, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "/home/appuser/.local/lib/python3.13/site-packages/fastapi/routing.py", line 345, in app
    solved_result = await solve_dependencies(
                    ^^^^^^^^^^^^^^^^^^^^^^^^^
    solved_result = await solve_dependencies(
                    ^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<9 lines>...
    )
    ^
  File "/home/appuser/.local/lib/python3.13/site-packages/fastapi/dependencies/utils.py", line 643, in solve_dependencies
    solved = await call(**solved_result.values)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/auth/zitadel.py", line 320, in get_current_user
    return await auth.get_user_from_token(credentials.credentials)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/auth/zitadel.py", line 281, in get_user_from_token
    claims = await self.validate_token(token)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/auth/zitadel.py", line 220, in validate_token
    signing_key = self._get_signing_key(token, jwks)
  File "/app/app/auth/zitadel.py", line 177, in _get_signing_key
    unverified_header = jwt.get_unverified_header(token)
  File "/home/appuser/.local/lib/python3.13/site-packages/jose/jwt.py", line 202, in get_unverified_header
    raise JWTError("Error decoding token headers.")
jose.exceptions.JWTError: Error decoding token headers.