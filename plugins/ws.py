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
        self.active = set()

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

        try:
            _LOGGER.info(f'NEW: subscriber {ws}')
            ### not the correct value to add, but placeholder.
            self.active.add(request.remote)

            # Hold the connection open, and process incoming messages.
            async for msg in ws:
                await self.receive(ws, msg)

        finally:
            self.active.discard(request.remote)
            _LOGGER.info(f'ENDED: subscriber {ws}')

        ### do we need a return value?
        return ws

    async def publish(self, payload):
        ### send PAYLOAD to all qualifying active connections
        pass

    async def publish_to(self, payload, who):
        ### find all active connections for WHO, and deliver PAYLOAD
        pass

    async def receive(self, ws, msg):
        print(f'FROM: {ws}; MSG: {msg}')

        ### do real parsing of what was sent. JSON, maybe?

        if msg.type == aiohttp.WSMsgType.TEXT:
            if msg.data == 'close':
                await ws.close()
            else:
                await ws.send_str(msg.data + '/answer')
        elif msg.type == aiohttp.WSMsgType.ERROR:
            print('ws connection closed with exception %s' %
                  ws.exception())
