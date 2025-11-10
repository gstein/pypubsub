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

"""matrix.py - test a full matrix of publishers and subscribers."""

import sys
import argparse
import pathlib
import logging
import asyncio

import yaml
from easydict import EasyDict as edict
import asfpy.pubsub
import aiohttp

# Ensure the path is set up for importing pypubsub and plugins.
THIS_DIR = pathlib.Path(__file__).resolve().parent
# One level above for the path.
sys.path.insert(0, THIS_DIR.parent)

# This will also import from plugins/
import pypubsub


DATE_FORMAT = '%m/%d %H:%M'
_LOGGER = logging.getLogger(__name__)

CFG_FILE = THIS_DIR / 'matrix.yaml'
ACL_FILE = THIS_DIR / '_no_acl_file'  # not needed
CFG = edict(yaml.safe_load(open(CFG_FILE)))

# How many items to publish for this test?
N_PUBLISH = 5


class DataCollector:
    "Collect expected pings from subscriptions."

    def __init__(self, host, port, tls_port=None, ws_port=None):
        self.host = host
        self.port = port
        self.tls_port = tls_port
        self.ws_port = ws_port

        self.datums = [ ]
        self.completed = asyncio.Event()  # we received everything

        self.tasks = [ ]

    def heard(self, channel, payload):
        _LOGGER.debug(f'HEARD on "{channel}": {payload}')
        self.datums.append((channel, payload['value']))

        channels = (1
                    + int(self.tls_port is not None)
                    + int(self.ws_port is not None)
                    )
        if len(self.datums) == channels * N_PUBLISH:
            _LOGGER.info('DONE. All items received.')
            self.completed.set()

    def create_tasks(self, loop):
        self.tasks.append(loop.create_task(self.client_http(), name='LISTEN:http'))
        if self.tls_port:
            self.tasks.append(loop.create_task(self.client_https(), name='LISTEN:http'))
        if self.ws_port:
            self.tasks.append(loop.create_task(self.client_ws(), name='LISTEN:http'))
        self.tasks.append(loop.create_task(self.pub_generate(), name='GENERATE'))

    async def client_http(self):
        _LOGGER.info('LISTENING: http')
        url = f'http://{self.host}:{self.port}/'
        async for payload in asfpy.pubsub.listen(url):
            if 'stillalive' in payload:
                _LOGGER.debug('stillalive received (http)')
                continue
            self.heard('http', payload)

    async def client_https(self):
        _LOGGER.info('LISTENING: https')
        url = f'https://{self.host}:{self.tls_port}/'
        async for payload in asfpy.pubsub.listen(url):
            if 'stillalive' in payload:
                _LOGGER.debug('stillalive received (https)')
                continue
            self.heard('https', payload)

    async def client_ws(self):
        _LOGGER.info('LISTENING: ws')
        url = f'https://{self.host}:{self.ws_port}/'
        async for payload in websocket_thingie:
            if 'stillalive' in payload:
                _LOGGER.debug('stillalive received (ws)')
                continue
            self.heard('ws', payload)

    async def pub_generate(self):
        _LOGGER.info('GENERATE: starting...')

        # Wait for the server to start up.
        ### would be nice if the server had an Event.
        await asyncio.sleep(3)

        url = f'http://{self.host}:{self.port}/'
        async with aiohttp.ClientSession() as s:

            for i in range(N_PUBLISH):
                payload = edict(value=i)
                _LOGGER.debug(f'Publishing: {payload}')
                async with s.put(url, json=payload) as r:
                    r.raise_for_status()
                    #print('RESPONSE:', (await r.text()).strip())

                # Not all at once ...
                await asyncio.sleep(1)


async def graceful_shutdown(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel all running tasks and wait for them to finish/cleanup."""

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    _LOGGER.debug(f"Cancelling {len(tasks)} pending tasks...")
    for t in tasks:
        t.cancel()

    # Wait for tasks to handle cancellation (they should catch CancelledError)
    await asyncio.gather(*tasks, return_exceptions=True)

    _LOGGER.debug("All tasks cancelled. Stopping loop...")
    loop.stop()


def main(argv):

    # PLAN: set up a DataCollector, and it will look for "all the events".
    # One task will push all those events. Goal is to exercise the paths
    # towards subscribing to events, and for publishing events.
    dc = DataCollector(CFG.server.bind, CFG.server.port)

    # Construct the loop we're going to use for testing.
    loop = asyncio.new_event_loop()

    # Create all the tasks for sending/receivving datums.
    dc.create_tasks(loop)

    server = pypubsub.Server(edict(config=CFG_FILE, acl=ACL_FILE))
    loop.create_task(server.server_loop(loop))

    # When all datums have been received, we're done.
    try:
        loop.run_until_complete(dc.completed.wait())

        # It finished!
        loop.run_until_complete(graceful_shutdown(loop))

    except KeyboardInterrupt:
        _LOGGER.info('INTERRUPT: Shutting down ...')
        loop.run_until_complete(graceful_shutdown(loop))


if __name__ == '__main__':
    # Set up logging. INFO everybody, DEBUG self.
    logging.basicConfig(level=logging.INFO,
                        style='{',
                        format='[{asctime}|{levelname}|{module}] {message}',
                        datefmt=DATE_FORMAT,
                        )
    _LOGGER.setLevel(logging.DEBUG)

    main(sys.argv[1:])
