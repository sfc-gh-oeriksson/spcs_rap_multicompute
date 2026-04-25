from flask import Blueprint, request, abort, make_response, jsonify
import datetime
import snowflake.snowpark.functions as f

import spcs_helpers

# Roles allowed for USE ROLE switching (allowlist prevents injection)
ALLOWED_ROLES = {'EAP_ROLE1', 'EAP_ROLE2'}

# Fallback service-level session (used when no user token is present, e.g. local dev)
_service_session = spcs_helpers.session()

snowpark = Blueprint('snowpark', __name__)

dateformat = '%Y-%m-%d'


def _get_session(role=None):
    """Return a per-request user session if an OAuth token is in the request headers.
    Falls back to a service-token session with the requested role (if any),
    or the default service session."""
    user_token = request.headers.get('Sf-Context-Current-User-Token')
    print(f"[_get_session] token_present={bool(user_token)} role={role}", flush=True)
    if user_token:
        return spcs_helpers.session_with_user_token(user_token, role), True
    if role:
        return spcs_helpers.session_for_role(role), True
    return _service_session, False


@snowpark.route('/whoami')
def whoami():
    sess, owned = _get_session()
    try:
        row = sess.sql("SELECT CURRENT_USER() AS u, CURRENT_ROLE() AS r").collect()[0]
        return make_response(jsonify({
            'user': row['U'],
            'role': row['R']
        }))
    except Exception:
        abort(500, "Error fetching identity from Snowflake.")
    finally:
        if owned:
            sess.close()


@snowpark.route('/top_clerks')
def top_clerks():
    sdt_str = request.args.get('start_range') or '1995-01-01'
    edt_str = request.args.get('end_range') or '1995-03-31'
    topn_str = request.args.get('topn') or '10'
    role_param = request.args.get('role')

    # Validate role against allowlist
    role = role_param if role_param in ALLOWED_ROLES else None

    try:
        sdt = datetime.datetime.strptime(sdt_str, dateformat)
        edt = datetime.datetime.strptime(edt_str, dateformat)
        topn = int(topn_str)
    except Exception:
        abort(400, "Invalid arguments.")

    sess, owned = _get_session(role)
    try:
        df = sess.table('EAP_DEMO.PUBLIC.ORDERS_VIEW') \
                .filter(f.col('O_ORDERDATE') >= sdt) \
                .filter(f.col('O_ORDERDATE') <= edt) \
                .group_by(f.col('O_CLERK')) \
                .agg(
                    f.sum(f.col('O_TOTALPRICE')).as_('CLERK_TOTAL'),
                    f.min(f.col('O_ORDERDATE')).as_('EARLIEST_ORDER'),
                    f.max(f.col('O_ORDERDATE')).as_('LATEST_ORDER'),
                ) \
                .order_by(f.col('CLERK_TOTAL').desc()) \
                .limit(topn)
        return make_response(jsonify([x.as_dict() for x in df.to_local_iterator()]))
    except Exception:
        abort(500, "Error reading from Snowflake. Check the logs for details.")
    finally:
        if owned:
            sess.close()
