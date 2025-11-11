#!/usr/bin/env python3
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

""" This is the WebSockets component of PyPubSub """

import asyncio
import logging

import aiohttp.web

_LOGGER = logging.getLogger(__name__)


class WebSocketWorker:

    def __init__(self, pubsub: 'pypubsub.Server'):
        self.pubsub = pubsub

        # The active connections/subscribers.
        # NOTE: set is more appropriate, but requires hashability.
        self.active = [ ]

    async def worker(self, host: str, port: int):
        # Now that we have a loop, construct the Server
        server = aiohttp.web.Server(self.handle_request)

        # The runner handles the Server, and the TCP port handling
        runner = aiohttp.web.ServerRunner(server)
        await runner.setup()

        site = aiohttp.web.TCPSite(runner, host, port)
        await site.start()
        _LOGGER.info('==== Serving up PubSub WebSocket goodness at'
                     f' {host}:{port} ====')

        ### not sure about this. maybe above creates a task, so we
        ### can exit? ... might need to retain references to the
        ### localvars to keep them alive.
        while True:
            await asyncio.sleep(10000)

    async def handle_request(self, request: aiohttp.web.BaseRequest):
        ws = aiohttp.web.WebSocketResponse()
        await ws.prepare(request)

        # Subscriber to wrap this WS connection.
        sub = WSSubscriber(ws, request.path)

        try:
            _LOGGER.info(f'NEW: subscriber {sub}')
            self.active.append(sub)

            # Hold the connection open, and process incoming messages.
            async for msg in ws:
                await self.receive(ws, msg)

        finally:
            try:
                self.active.remove(sub)
            except ValueError:
                # Something else removed it? Meh. Keep going.
                pass
            _LOGGER.info(f'ENDED: subscriber {sub}')

        ### do we need a return value?
        return ws

    async def publish(self, payload):
        ### send PAYLOAD to all qualifying active connections
        ### for now: PAYLOAD is a simple text string.
        for sub in self.active:
            print('SUB:', sub, payload)
            await sub.write(payload)

    async def publish_to(self, payload, who):
        ### find all active connections for WHO, and deliver PAYLOAD
        pass

    async def receive(self, ws, msg):
        print(f'FROM: {ws}; MSG: {msg}')

        ### do real parsing of what was sent. JSON, maybe?

        if msg.type == aiohttp.WSMsgType.TEXT:
            if msg.data == 'close':
                await ws.close()
            elif msg.data == 'push':
                loop = asyncio.get_running_loop()
                def invoke_publish():
                    loop.create_task(self.publish('pushed-data'))
                loop.call_later(2.0, invoke_publish)
            else:
                await ws.send_str(msg.data + '/answer')
        elif msg.type == aiohttp.WSMsgType.ERROR:
            print('ws connection closed with exception %s' %
                  ws.exception())


class WSSubscriber:

    def __init__(self, ws, path):
        self.ws = ws

        self.topics = set()
        for group in path.split(','):
            parts = tuple(t for t in group.split('/') if t)
            self.topics.add(parts)

        # Used to ensure only one server-push at a time.
        self.send_lock = asyncio.Lock()

    async def write(self, content):
        async with self.send_lock:
            await self.ws.send_str(content)
