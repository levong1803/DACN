import asyncio

from app import db
from app.agent import run_chat


async def main() -> None:
    await db.init_db()
    reply, sid = await run_chat("test no key")
    print("ok", len(reply), sid[:8])


if __name__ == "__main__":
    asyncio.run(main())
