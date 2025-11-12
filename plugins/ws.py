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

import sys
import asyncio
import logging
import json
import dataclasses

import aiohttp.web
#from easydict import EasyDict as edict

_LOGGER = logging.getLogger(__name__)

WS_CLOSE_INVALID_PAYLOAD = 1003   # or UNSUPPORTED_DATA
WS_CLOSE_POLICY_VIOLATION = 1008  # maps to HTTP 403


@dataclasses.dataclass
class WebSocketCloseError(Exception):
    "Any error that occurs during process, will close the websocket."
    code: int = WS_CLOSE_INVALID_PAYLOAD
    message: str = "Bad request"


class WebSocketWorker:

    def __init__(self, pubsub: 'pypubsub.Server'):
        self.pubsub = pubsub

        # Shorthand for the server's config.
        ### we might want edict for some of this stuff.
        self.config = pubsub.config

        # The active connections/subscribers.
        # NOTE: set is more appropriate, but requires hashability.
        self.active = [ ]

        # Find the pubsub module, and make it a global now, for later
        # use and operation.
        global pypubsub
        pypubsub = sys.modules[pubsub.__module__]
        #print(f'PYPUBSUB:', pypubsub)

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
        sub = WSSubscriber(ws, request.path, request.remote, self.config)

        try:
            _LOGGER.info(f'NEW: subscriber {sub}')
            self.active.append(sub)

            # Hold the connection open, and process incoming messages.
            async for msg in ws:
                await self.receive(sub, msg)

        except WebSocketCloseError as e:
            await ws.close(code=e.code, message=e.message)
        finally:
            try:
                self.active.remove(sub)
            except ValueError:
                # Something else removed it? Meh. Keep going.
                pass
            _LOGGER.info(f'ENDED: subscriber {sub}')

        # Return the websocket for cleanup, logging, etc.
        return ws

    async def publish(self, payload):
        ### send PAYLOAD to all qualifying active connections
        ### for now: PAYLOAD is a simple text string.
        for sub in self.active:
            print('SUB:', sub, payload)
            ### content = json.dumps(payload)
            await sub.write(payload)

    async def publish_to(self, payload, who):
        ### find all active connections for WHO, and deliver PAYLOAD
        pass

    async def receive(self, sub, msg):
        ws = sub.ws
        print(f'FROM: {ws}; MSG: {msg}')

        if msg.type == aiohttp.WSMsgType.TEXT:

            try:
                event = json.loads(msg.data)
            except json.JSONDecodeError:
                raise WebSocketCloseError(WS_CLOSE_INVALID_PAYLOAD,
                                          'Message must be valid JSON')

            if not isinstance(event, dict) or 'op' not in event:
                raise WebSocketCloseError(WS_CLOSE_INVALID_PAYLOAD,
                                          '"op" field is missing')
            op = event['op']

            if op == 'close':
                # Client-direction to have the server close the connection.
                await ws.close()
            elif op == 'publish':
                # A publish event.

                topic = event['topic']  # Assume it is present

                # Are we allowed to publish this?
                if not sub.may_publish:
                    raise WebSocketCloseError(WS_CLOSE_POLICY_VIOLATION,
                                              pypubsub.PUBSUB_NOT_ALLOWED)
                ### now examine secure_topics

                loop = asyncio.get_running_loop()
                def invoke_publish():
                    loop.create_task(self.publish('pushed-data'))
                loop.call_later(2.0, invoke_publish)
            elif op == 'ping':
                # Client-initiated ping/pong.
                await sub.write('"pong"')  # JSON string
            elif op == 'simple':
                msg = event['msg']  # assume it is present
                await sub.write(msg + '/reply')
            else:
                # Do not include OP, to avoid potential injection issues.
                raise WebSocketCloseError(WS_CLOSE_INVALID_PAYLOAD,
                                          '"op" field value is unknown')
 
        elif msg.type == aiohttp.WSMsgType.ERROR:
            print('ws connection closed with exception %s' %
                  ws.exception())


class WSSubscriber:

    def __init__(self, ws, path, remote_ip, server_config):
        self.ws = ws

        # What topic(s) did this connection subscribe to?
        self.topics = set()
        for group in path.split(','):
            parts = tuple(t for t in group.split('/') if t)
            self.topics.add(parts)

        # Publishing is based on your IP. Not all WS connections will
        # be allowed to publish.
        self.may_publish = ip_may_publish(remote_ip, server_config)
        ### is there a way to better identify the subscriber? IP? authn?
        ### include the IP in this log?
        _LOGGER.info('Subscriber may'
                     f'{"" if self.may_publish else " NOT"}'
                     ' publish events')

        # Capture the server_config's "secure topics" for consideration
        # later, on whether this Subscriber can publish to them.
        pass

        # Used to ensure only one server-push at a time.
        self.send_lock = asyncio.Lock()

    async def write(self, content: str):
        "Write CONTENT to the Subscriber client."

        async with self.send_lock:
            await self.ws.send_str(content)


def ip_may_publish(ip, server_config):
    "Is this IP allowed to publish events?"
    for network in server_config.payloaders:
        if ip in network:
            return True
    return False
