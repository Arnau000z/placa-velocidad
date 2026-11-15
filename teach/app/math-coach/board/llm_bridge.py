#!/usr/bin/env python3
"""Lets App Lab apps reach the language model without exposing it to the network.

llama-server (math-llm.service) listens on 127.0.0.1:8081 only, on purpose. An App Lab app
runs in a Docker container, where 127.0.0.1 is the container itself. This forwarder listens
on the Docker host address (docker0, 172.17.0.1, which the containers see as
'msgpack-rpc-router') and relays every connection to 127.0.0.1:8081. It never listens on
Wi-Fi or Ethernet. Standard library only. Runs as a user service: math-llm-bridge.service.
"""
import asyncio
import os

LISTEN_HOST = os.environ.get("BRIDGE_HOST", "172.17.0.1")
LISTEN_PORT = int(os.environ.get("BRIDGE_PORT", "8081"))
TARGET = ("127.0.0.1", int(os.environ.get("BRIDGE_TARGET_PORT", "8081")))


async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def handle(client_reader, client_writer):
    try:
        target_reader, target_writer = await asyncio.open_connection(*TARGET)
    except OSError:
        client_writer.close()
        return
    await asyncio.gather(pipe(client_reader, target_writer), pipe(target_reader, client_writer))


async def main():
    while True:  # at boot, docker0 may not have its address yet
        try:
            server = await asyncio.start_server(handle, LISTEN_HOST, LISTEN_PORT)
            break
        except OSError as error:
            print(f"waiting for {LISTEN_HOST}:{LISTEN_PORT} ({error})", flush=True)
            await asyncio.sleep(5)
    print(f"forwarding {LISTEN_HOST}:{LISTEN_PORT} -> {TARGET[0]}:{TARGET[1]}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
