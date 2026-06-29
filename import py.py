#download ffmoeg if not working
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import time
import lyricsgenius

# ⚠️ ВСТАВЬТЕ СЮДА ВАШИ ТОКЕНЫ
TOKEN = "Enter_you_discordbot_token"
# YOO I Gift you mi genius token
GENIUS_TOKEN = "PhN_rIKyB4t_YWguFmh_yJVlCK2NNPbQt8Qs0p0cr-tAq9m8YkiBnWIoYP2pJ0JF"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=">", intents=intents)

genius = lyricsgenius.Genius(GENIUS_TOKEN, remove_section_headers=True, skip_non_songs=True)

# Глобальные переменные для работы плеера и очереди
music_queue = []
current_track_title = ""

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    'extractor_args': {'youtube': {'player_client': ['default', '-tv', 'web_safari', 'web_embedded']}},
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

def format_time(seconds):
    if not seconds: return "00:00"
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"

def make_bar(current, total, length=12):
    if not total: return "▬" * length
    percent = current / total
    filled = int(percent * length)
    filled = max(0, min(length, filled))
    return "▬" * filled + "🔘" + "▬" * (length - filled - 1)


# GUI ЭЛЕМЕНТ: Пульт управления кнопками
class AdvancedMusicView(discord.ui.View):
    def __init__(self, vc, title, url, duration, thumbnail, author_ctx):
        super().__init__(timeout=None)
        self.vc = vc
        self.title = title
        self.url = url
        self.duration = duration
        self.thumbnail = thumbnail
        self.author_ctx = author_ctx
        self.start_time = time.time()
        self.paused_time = 0
        self.total_paused = 0
        self.message = None
        self.is_active = True
        self.current_volume = 1.0  # 100% громкость по умолчанию
        bot.loop.create_task(self.update_player_loop())

    async def update_player_loop(self):
        while self.is_active and self.vc.is_connected():
            if self.vc.is_playing():
                current_loc = time.time() - self.start_time - self.total_paused
                if self.duration and current_loc > self.duration:
                    current_loc = self.duration
                    
                bar_str = make_bar(current_loc, self.duration)
                time_str = f"{format_time(current_loc)} / {format_time(self.duration)}"
                vol_str = f"Громкость: {int(self.current_volume * 100)}%"
                
                embed = discord.Embed(
                    title="🎵 Сейчас играет", 
                    description=f"**[{self.title}]({self.url})**\n\n`{bar_str}`  *{time_str}*\n`{vol_str}`", 
                    color=discord.Color.green()
                )
                if self.thumbnail: embed.set_thumbnail(url=self.thumbnail)
                embed.set_footer(text=f"Запросил: {self.author_ctx.author.name} | В очереди: {len(music_queue)} треков")
                
                try:
                    if self.message: await self.message.edit(embed=embed)
                except Exception:
                    break
            await asyncio.sleep(20)

    @discord.ui.button(label="⏸️ Пауза / Старт", style=discord.ButtonStyle.blurple)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_ctx.author.id:
            await interaction.response.send_message("❌ Ты не достаточно фембойчик милий мальчик как владелец", ephemeral=True)
            return

        if self.vc.is_playing():
            self.vc.pause()
            self.paused_time = time.time()
            await interaction.response.send_message("⏸️ Музыка на паузе.", ephemeral=True)
        elif self.vc.is_paused():
            self.vc.resume()
            self.total_paused += time.time() - self.paused_time
            await interaction.response.send_message("▶️ Продолжаем.", ephemeral=True)
        else:
            await interaction.response.send_message("Ничего не играет.", ephemeral=True)

    @discord.ui.button(label="🔉 Тише", style=discord.ButtonStyle.gray)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_ctx.author.id:
            await interaction.response.send_message("❌ Ты не достаточно фембойчик милий мальчик как владелец", ephemeral=True)
            return

        if self.vc.source:
            self.current_volume = max(0.0, self.current_volume - 0.2)
            self.vc.source.volume = self.current_volume
            await interaction.response.send_message(f"🔉 Громкость уменьшена до {int(self.current_volume*100)}%", ephemeral=True)
        else:
            await interaction.response.send_message("Аудиопоток не найден.", ephemeral=True)

    @discord.ui.button(label="🔊 Громче", style=discord.ButtonStyle.gray)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_ctx.author.id:
            await interaction.response.send_message("❌ Ты не достаточно фембойчик милий мальчик как владелец", ephemeral=True)
            return

        if self.vc.source:
            self.current_volume = min(2.0, self.current_volume + 0.2)
            self.vc.source.volume = self.current_volume
            await interaction.response.send_message(f"🔊 Громкость увеличена до {int(self.current_volume*100)}%", ephemeral=True)
        else:
            await interaction.response.send_message("Аудиопоток не найден.", ephemeral=True)

    @discord.ui.button(label="⏭️ Пропустить", style=discord.ButtonStyle.green)
    async def skip_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_ctx.author.id:
            await interaction.response.send_message("❌ Ты не достаточно фембойчик милий мальчик как владелец", ephemeral=True)
            return

        if self.vc.is_playing() or self.vc.is_paused():
            self.vc.stop()
            await interaction.response.send_message("⏭️ Включаю следующий трек.", ephemeral=True)
        else:
            await interaction.response.send_message("В очереди больше ничего нет.", ephemeral=True)

    @discord.ui.button(label="⏹️ Стоп", style=discord.ButtonStyle.red)
    async def stop_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_ctx.author.id:
            await interaction.response.send_message("❌ Ты не достаточно фембойчик милий мальчик как владелец", ephemeral=True)
            return

        global current_track_title, music_queue
        music_queue.clear()
        if self.vc.is_playing() or self.vc.is_paused():
            self.vc.stop()
            self.is_active = False
            current_track_title = ""
            await interaction.response.send_message("⏹️ Воспроизведение полностью остановлено, очередь очищена.", ephemeral=True)
        else:
            await interaction.response.send_message("Музыка не активна.", ephemeral=True)


def play_next_in_queue(ctx, vc):
    global current_track_title
    if len(music_queue) > 0:
        next_track = music_queue.pop(0)
        current_track_title = next_track['title']

        raw_source = discord.FFmpegPCMAudio(executable="ffmpeg.exe", source=next_track['stream_url'], **FFMPEG_OPTIONS)
        audio_source = discord.PCMVolumeTransformer(raw_source)
        vc.play(audio_source, after=lambda e: play_next_in_queue(ctx, vc))

        embed = discord.Embed(title="⏭️ Следующий трек из очереди", description=f"**[{next_track['title']}]({next_track['url']})**", color=discord.Color.green())
        if next_track['thumbnail']: embed.set_thumbnail(url=next_track['thumbnail'])
        
        view = AdvancedMusicView(vc, next_track['title'], next_track['url'], next_track['duration'], next_track['thumbnail'], ctx)
        
        async def send_new_view():
            view.message = await ctx.send(embed=embed, view=view)
        bot.loop.create_task(send_new_view())


@bot.event
async def on_ready():
    print(f"Робот {bot.user.name} успешно запущен с GUI-пультом, очередью и громкостью!")


@bot.command()
async def play(ctx, *, search: str):
    global current_track_title
    if ctx.author.voice is None:
        await ctx.send("Сначала зайдите в голосовой канал!")
        return

    voice_channel = ctx.author.voice.channel
    vc = ctx.voice_client if ctx.voice_client else await voice_channel.connect()

    status_msg = await ctx.send(f"🔍 Ищу и обрабатываю: `{search}`...")

    if not search.startswith("http"):
        search = f"ytsearch:{search}"

    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(search, download=False)
            if 'entries' in info:
                info = info['entries'] if isinstance(info['entries'], list) else info['entries']
                
            stream_url = info['url']
            title = info.get('title', 'Аудио')
            url = info.get('webpage_url', 'https://youtube.com')
            duration = info.get('duration', 0)
            thumbnail = info.get('thumbnail', None)
        except Exception as e:
            await status_msg.edit(content="❌ Ничего не найдено по вашему запросу.")
            print(f"Ошибка поиска: {e}")
            return

    if vc.is_playing() or vc.is_paused():
        music_queue.append({
            'stream_url': stream_url, 'title': title, 'url': url, 
            'duration': duration, 'thumbnail': thumbnail
        })
        await status_msg.edit(content=f"📝 Добавлено в queue: **{title}** (Место: {len(music_queue)})")
        return

    try:
        current_track_title = title
        raw_source = discord.FFmpegPCMAudio(executable="ffmpeg.exe", source=stream_url, **FFMPEG_OPTIONS)
        audio_source = discord.PCMVolumeTransformer(raw_source)
        
        vc.play(audio_source, after=lambda e: play_next_in_queue(ctx, vc))
        await status_msg.delete()

        bar_str = make_bar(0, duration)
        time_str = f"00:00 / {format_time(duration)}"
        vol_str = "Громкость: 100%"
        
        embed = discord.Embed(title="🎵 Сейчас играет", description=f"**[{title}]({url})**\n\n`{bar_str}`  *{time_str}*\n`{vol_str}`", color=discord.Color.green())
        if thumbnail: 
            embed.set_thumbnail(url=thumbnail)
        embed.set_footer(text=f"Запросил: {ctx.author.name}", icon_url=ctx.author.display_avatar.url)

        view = AdvancedMusicView(vc, title, url, duration, thumbnail, ctx)
        view.message = await ctx.send(embed=embed, view=view)

        bot.loop.create_task(auto_leave_checker(ctx, vc, view))

    except Exception as e:
        await ctx.send("❌ Ошибка работы аудио-движка FFmpeg.")
        print(f"Ошибка: {e}")


@bot.command()
async def queue(ctx):
    if len(music_queue) == 0:
        await ctx.send("Очередь пуста! Добавьте музыку через команду `>play`")
        return
    
    text_queue = ""
    for i, track in enumerate(music_queue[:10], 1):
        text_queue += f"{i}. **{track['title']}**\n"
        
    embed = discord.Embed(title="📋 Текущая очередь музыки", description=text_queue, color=discord.Color.orange())
    await ctx.send(embed=embed)


@bot.command()
async def text(ctx, *, song_name: str = None):
    global current_track_title
    target_song = song_name if song_name else current_track_title

    if not target_song:
        await ctx.send("❌ Сейчас ничего не играет. Укажите название: `>text Название песни`")
        return

    msg = await ctx.send(f"🔍 Ищу текст для: `{target_song}`...")

    try:
        song = genius.search_song(target_song)
        if song and song.lyrics:
            lyrics = song.lyrics
            if len(lyrics) > 1900:
                lyrics = lyrics[:1900] + "\n\n*(текст обрезан из-за лимитов Discord)*"

            embed = discord.Embed(title=f"🎤 Текст песни: {song.title}", description=lyrics, color=discord.Color.blue())
            embed.set_footer(text=f"Исполнитель: {song.artist}")
            await msg.delete()
            await ctx.send(embed=embed)
        else:
            await msg.edit(content=f"❌ Текст для песни `{target_song}` не найден.")
    except Exception as e:
        await msg.edit(content="❌ Произошла ошибка при поиске текста.")
        print(f"Ошибка команды text: {e}")


async def auto_leave_checker(ctx, vc, view):
    global current_track_title
    while vc.is_playing() or vc.is_paused() or len(music_queue) > 0:
        await asyncio.sleep(5)
    
    await asyncio.sleep(180)
    if vc.is_connected() and not vc.is_playing():
        view.is_active = False
        current_track_title = ""
        await vc.disconnect()
        await ctx.send("💤 Вышел из канала из-за неактивности.")


bot.run(TOKEN)
