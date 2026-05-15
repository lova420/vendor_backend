import asyncio
import sys

# psycopg's async driver requires SelectorEventLoop; Windows defaults to
# ProactorEventLoop, which raises InterfaceError on any async DB call.
# Set the policy at package import so it's in place before uvicorn creates
# the loop (this module loads before app.main).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
