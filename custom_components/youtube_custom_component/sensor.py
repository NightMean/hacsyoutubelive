"""
A platform which give you info about the newest video on a channel.

For more details about this component, please refer to the documentation at
https://github.com/custom-components/youtube
"""

import logging
import async_timeout
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.helpers.entity import Entity
from dateutil.parser import parse
import re
import html
from datetime import timedelta
from datetime import datetime

CONF_CHANNEL_ID = 'channel_id'
CONF_LIVE_ONLY = 'live_only'

ICON = 'mdi:youtube'

BASE_URL = 'https://www.youtube.com/feeds/videos.xml?channel_id={}'
CHANNEL_LIVE_URL = 'https://www.youtube.com/channel/{}'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_CHANNEL_ID): cv.string,
    vol.Optional(CONF_LIVE_ONLY): cv.boolean,
})

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)

async def async_setup_platform(
        hass, config, async_add_entities, discovery_info=None):  # pylint: disable=unused-argument
    """Setup sensor platform."""
    channel_id = config[CONF_CHANNEL_ID]
    live_only = config[CONF_LIVE_ONLY]
    session = async_create_clientsession(hass)
    try:
        url = BASE_URL.format(channel_id)
        async with async_timeout.timeout(10):
            response = await session.get(url)
            info = await response.text()
        name = info.split('<title>')[1].split('</')[0]
    except Exception as error:  # pylint: disable=broad-except
        _LOGGER.debug('Unable to set up - %s', error)
        name = None

    if name is not None:
        async_add_entities([YoutubeSensor(channel_id, live_only, name, session)], True)

class YoutubeSensor(Entity):
    """YouTube Sensor class"""
    def __init__(self, channel_id, live_only, name, session):
        self._state = None
        self.session = session
        self._image = None
        self.stars = 0
        self.views = 0
        self.stream = False
        self.live = False
        self._name = name
        self.channel_id = channel_id
        self._live_only = live_only
        self.url = None
        self.embed_url = None
        self.content_id = None
        self.published = None
        self.channel_live = False
        self.channel_image = None
        self.expiry = parse('01 Jan 1900 00:00:00 UTC')
        self.stream_start = None   
        self.last_update = None

    async def async_update(self):
        """Update sensor."""
        _LOGGER.debug('%s - Running update', self._name)
        try:
            url = BASE_URL.format(self.channel_id)
            async with async_timeout.timeout(10):
                response = await self.session.get(url)
                info = await response.text()
            exp = parse(response.headers['Expires'])
            """if exp < self.expiry:
                return"""
            self.expiry = exp
            self.last_update = datetime.now()
            ok = False
            for video in info.split('<entry>')[1:]:
                title = video.split('<title>')[1].split('</')[0]
                url = video.split('<link rel="alternate" href="')[1].split('"/>')[0]
                stream, live, stream_start = await is_live(url, self._name, self.hass, self.session)
                if (self._live_only and live) or (not self._live_only):
                    if url != self.url:
                        self.url = url
                        self.embed_url = 'https://www.youtube.com/embed/' + url.split('v=')[1].split('&')[0]
                        self.live = live
                        self.stream = stream
                        self.stream_start = stream_start
                        self.content_id = url.split('?v=')[1]
                        self.published = video.split('<published>')[1].split('</')[0]
                        thumbnail_url = video.split('<media:thumbnail url="')[1].split('"')[0]
                        self._state = html.unescape(title)
                        self._image = thumbnail_url
                        self.stars = video.split('<media:starRating count="')[1].split('"')[0]
                        self.views = video.split('<media:statistics views="')[1].split('"')[0]
                        url = CHANNEL_LIVE_URL.format(self.channel_id)
                        self.channel_live, self.channel_image = await is_channel_live(url, self.name, self.hass, self.session)
                    ok = True
                    break;
                else:
                    """break;"""
            if not ok:
                """No videos found, reset live flags incase of live_only checks"""
                self.live = False
                self.channel_live = False
        except Exception as error:  # pylint: disable=broad-except
            _LOGGER.debug('%s - Could not update - %s', self._name, error)

    @property
    def name(self):
        """Name."""
        return self._name

    @property
    def entity_picture(self):
        """Picture."""
        return self._image

    @property
    def state(self):
        """State."""
        return self._state

    @property
    def unique_id(self):
        """Return unique ID for this sensor."""
        return self.channel_id

    @property
    def icon(self):
        """Icon."""
        return ICON

    @property
    def extra_state_attributes(self):
        """Attributes."""
        return {'url': self.url,
                'embed_url': self.embed_url,
                'content_id': self.content_id,
                'published': self.published,
                'stars': self.stars,
                'views': self.views,
                'stream': self.stream,
                'stream_start': self.stream_start,
                'live': self.live,
                'channel_is_live': self.channel_live,
                'channel_image': self.channel_image,
                'last_update': self.last_update}

async def is_live(url, name, hass, session):
    """Return bool if video is stream and bool if video is live"""
    live = False
    stream = False
    start = None
    try:
        async with async_timeout.timeout(10):
            response = await session.get(url, cookies=dict(CONSENT="YES+cb"))
            info = await response.text()
        if 'isLiveBroadcast' in info:
            stream = True
            start = parse(info.split('startDate" content="')[1].split('"')[0])
            if 'endDate' not in info:
                live = True
                _LOGGER.debug('%s - Latest Video is live', name)
    except Exception as error:  # pylint: disable=broad-except
        _LOGGER.debug('%s - Could not update - %s', name, error)
    return stream, live, start

async def is_channel_live(url, name, hass, session):
    """Return bool if channel is live"""
    live = False
    try:
        async with async_timeout.timeout(10):
            response = await session.get(url, cookies=dict(CONSENT="YES+cb"))
            info = await response.text()
        if '{"iconType":"LIVE"}' in info:
            live = True
            _LOGGER.debug('%s - Channel is live', name)
        regex = r"\"width\":48,\"height\":48},{\"url\":\"(.*?)\",\"width\":88,\"height\":88},{\"url\":"
        channel_image = re.findall(regex, info, re.MULTILINE)[0].replace("=s88-c-k-c0x00ffffff-no-rj", "")
    except Exception as error:  # pylint: disable=broad-except
        _LOGGER.debug('%s - Could not update - %s', name, error)
    return live, channel_image
