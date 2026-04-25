import os
import snowflake.connector
from snowflake.snowpark import Session

def connection() -> snowflake.connector.SnowflakeConnection:
    if os.path.isfile("/snowflake/session/token"):
        creds = {
            'host': os.getenv('SNOWFLAKE_HOST'),
            'port': os.getenv('SNOWFLAKE_PORT'),
            'protocol': "https",
            'account': os.getenv('SNOWFLAKE_ACCOUNT'),
            'authenticator': "oauth",
            'token': open('/snowflake/session/token', 'r').read(),
            'warehouse': os.getenv('SNOWFLAKE_WAREHOUSE'),
            'database': os.getenv('SNOWFLAKE_DATABASE'),
            'schema': os.getenv('SNOWFLAKE_SCHEMA'),
            'client_session_keep_alive': True
        }
    else:
        creds = {
            'account': os.getenv('SNOWFLAKE_ACCOUNT'),
            'user': os.getenv('SNOWFLAKE_USER'),
            'password': os.getenv('SNOWFLAKE_PASSWORD'),
            'warehouse': os.getenv('SNOWFLAKE_WAREHOUSE'),
            'database': os.getenv('SNOWFLAKE_DATABASE'),
            'schema': os.getenv('SNOWFLAKE_SCHEMA'),
            'client_session_keep_alive': True
        }

    conn = snowflake.connector.connect(**creds)
    return conn

def session() -> Session:
    return Session.builder.configs({"connection": connection()}).create()

def connection_with_user_token(user_token: str, role: str = None) -> snowflake.connector.SnowflakeConnection:
    creds = {
        'host': os.getenv('SNOWFLAKE_HOST'),
        'port': os.getenv('SNOWFLAKE_PORT'),
        'protocol': "https",
        'account': os.getenv('SNOWFLAKE_ACCOUNT'),
        'authenticator': "oauth",
        'token': user_token,
        'warehouse': os.getenv('SNOWFLAKE_WAREHOUSE'),
        'database': os.getenv('SNOWFLAKE_DATABASE'),
        'schema': os.getenv('SNOWFLAKE_SCHEMA'),
        'client_session_keep_alive': False
    }
    # Set role at connection time — more reliable than USE ROLE after connect,
    # which can be lost when Snowpark wraps the connection into a Session.
    if role:
        creds['role'] = role
    return snowflake.connector.connect(**creds)

def session_with_user_token(user_token: str, role: str = None) -> Session:
    conn = connection_with_user_token(user_token, role)
    return Session.builder.configs({"connection": conn}).create()

def session_for_role(role: str) -> Session:
    """Open a fresh service-token session with an explicit role.
    Used when no per-user OAuth token is available (e.g. SPCS token injection
    not configured). Requires the service role to have the target role granted."""
    if not os.path.isfile("/snowflake/session/token"):
        raise RuntimeError("No service token available for session_for_role()")
    creds = {
        'host': os.getenv('SNOWFLAKE_HOST'),
        'port': os.getenv('SNOWFLAKE_PORT'),
        'protocol': "https",
        'account': os.getenv('SNOWFLAKE_ACCOUNT'),
        'authenticator': "oauth",
        'token': open('/snowflake/session/token', 'r').read(),
        'warehouse': os.getenv('SNOWFLAKE_WAREHOUSE'),
        'database': os.getenv('SNOWFLAKE_DATABASE'),
        'schema': os.getenv('SNOWFLAKE_SCHEMA'),
        'role': role,
        'client_session_keep_alive': False
    }
    conn = snowflake.connector.connect(**creds)
    return Session.builder.configs({"connection": conn}).create()
