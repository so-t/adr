import asyncio
import logging
import config
import yt_dlp
import discord

from discord.ext import commands
from video import Video

FFMPEG_BEFORE_OPTS = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'

cfg = config.load_config()

intents = discord.Intents().all()
adm = commands.Bot(command_prefix=cfg["prefix"], intents=intents)

states = {}


async def is_playing(ctx):
    """Checks that audio is currently playing before continuing."""
    client = ctx.guild.voice_client
    return client and client.channel and client.source


def get_state(guild):
    """Gets the state for `guild`, creating it if it does not exist."""
    if guild.id in states:
        return states[guild.id]
    else:
        states[guild.id] = GuildState()
        return states[guild.id]


class GuildState:
    """Helper class managing per-guild state."""

    def __init__(self):
        self.volume = 1.0
        self.playlist = []
        self.skip_votes = set()
        self.now_playing = None

    def is_requester(self, user):
        return self.now_playing.requested_by == user


@adm.event
async def on_ready():
    logging.info(f"Logged in as {adm.user.name}")


@adm.command(help='Clears the current queue')
async def clear(ctx):
    state = get_state(ctx.guild)
    state.playlist = []
    return


@adm.command(help='Joins the voice channel')
async def join(ctx):
    if not ctx.message.author.voice:
        await ctx.send("{} is not connected to a voice channel".format(ctx.message.author.name))
        return
    else:
        channel = ctx.message.author.voice.channel
    await channel.connect()


@adm.command(help='Leaves the voice channel')
async def leave(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_connected():
        await voice_client.disconnect()
    else:
        await ctx.send("The bot is not connected to a voice channel.")


@adm.command(help='Pauses the current song')
async def pause(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        await voice_client.pause()
    else:
        await ctx.send("The bot is not playing anything at the moment.")


def _play_song(client, state, video):
    state.now_playing = video
    state.skip_votes = set()  # clear skip votes
    source = discord.PCMVolumeTransformer(
        discord.FFmpegPCMAudio(video.stream_url, before_options=FFMPEG_BEFORE_OPTS), volume=state.volume
    )

    def after_playing(err):
        if err:
            logging.warning(f'Error in after_playing() for {video}: {err}')
        if len(state.playlist) > 0:
            next_song = state.playlist.pop(0)
            _play_song(client, state, next_song)
        else:
            asyncio.run_coroutine_threadsafe(client.disconnect(),
                                             adm.loop)

    client.play(source, after=after_playing)


@adm.command(help='Plays audio from <url>.')
async def play(ctx, url=None):
    """Plays audio hosted at <url> (or performs a search for <url> and plays the first result)."""

    client = ctx.guild.voice_client
    state = get_state(ctx.guild)  # get the guild's state

    if client and client.channel:
        if url is None:
            await resume(ctx)
            return
        else:
            try:
                video = Video(url, ctx.author)
            except yt_dlp.DownloadError as err:
                logging.warning(f"Error downloading video: {err}")
                await ctx.send(
                    f'An error occurred during video download.'
                )
                return

        guild_is_playing = await is_playing(ctx)
        if not guild_is_playing:
            try:
                await ctx.send(
                    "Added to queue.", embed=video.get_embed()
                )
            except Exception as err:
                logging.warning(f'Error sending message: {err}')
                return
            else:
                _play_song(client, state, video)
        else:
            state.playlist.append(video)
            await ctx.send(
                "Added to queue.", embed=video.get_embed()
            )
    else:
        if ctx.author.voice is not None and ctx.author.voice.channel is not None:
            channel = ctx.author.voice.channel
            try:
                video = Video(url, ctx.author)
            except yt_dlp.DownloadError as err:
                logging.warning(f'Error downloading video: {err}')
                await ctx.send(
                    f'An error occurred during video download.')
                return
            client = await channel.connect()
            _play_song(client, state, video)
            await ctx.send(
                "", embed=video.get_embed()
            )
            logging.info(f"Now playing '{video.title}'")
        else:
            raise commands.CommandError(
                "You need to be in a voice channel to do that.")


@adm.command(help='Resumes the current song.')
async def resume(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_paused():
        await voice_client.resume()
    else:
        await ctx.send("The bot was not playing anything before this.")


@adm.command(help='Skips ahead to next song.')
async def skip(ctx):
    """Skips the currently playing song, or votes to skip it."""
    client = ctx.guild.voice_client
    state = get_state(ctx.guild)
    client.stop()


@adm.command(help='Stops the current song')
async def stop(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        await voice_client.stop()
    else:
        await ctx.send("The bot is not playing anything at the moment.")


if __name__ == "__main__":
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s"
    )
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler("bot.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if cfg["token"] == "":
        raise ValueError(
            "No token has been provided. Please ensure that config.toml contains the bot token."
        )
    adm.run(cfg["token"])
