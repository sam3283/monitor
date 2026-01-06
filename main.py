import discord
from discord.ext import commands, tasks
from discord import Embed
import aiohttp
import json
import os
import re
from datetime import datetime
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

class InstagramMonitor:
    def __init__(self):
        self.accounts_file = 'instagram_accounts.json'
        self.last_posts_file = 'last_posts.json'
        self.accounts = self.load_json(self.accounts_file)
        self.last_posts = self.load_json(self.last_posts_file)
        self.session = None
        
    def load_json(self, filename):
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
        return {}
    
    def save_json(self, filename, data):
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    def save_accounts(self):
        self.save_json(self.accounts_file, self.accounts)
    
    def save_last_posts(self):
        self.save_json(self.last_posts_file, self.last_posts)

monitor = InstagramMonitor()

@bot.event
async def on_ready():
    print(f'{bot.user} online')
    monitor.session = aiohttp.ClientSession()
    if monitor.accounts:
        check_instagram.start()

@tasks.loop(minutes=15)
async def check_instagram():
    for username, account_data in monitor.accounts.items():
        try:
            await check_account(username, account_data)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Error {username}: {e}")

async def check_account(username, account_data):
    user_data = await fetch_instagram_data(username)
    if not user_data:
        return
    
    posts = user_data.get('edge_owner_to_timeline_media', {}).get('edges', [])
    if not posts:
        return
    
    latest_post = posts[0]['node']
    post_id = latest_post['id']
    
    last_post_id = monitor.last_posts.get(username)
    if last_post_id != post_id:
        await send_notification(username, latest_post, user_data, account_data)
        monitor.last_posts[username] = post_id
        monitor.save_last_posts()

async def fetch_instagram_data(username):
    url = f"https://www.instagram.com/{username}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    async with monitor.session.get(url, headers=headers) as response:
        if response.status == 200:
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            script_tags = soup.find_all('script')
            for script in script_tags:
                if 'window._sharedData' in script.text:
                    json_text = script.text.split(' = ')[1].rstrip(';')
                    data = json.loads(json_text)
                    
                    user_data = data.get('entry_data', {}).get('ProfilePage', [{}])[0].get('graphql', {}).get('user')
                    return user_data
    return None

async def send_notification(username, post, user_data, account_data):
    channel_id = account_data.get('channel_id')
    if not channel_id:
        return
    
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return
    
    embed = Embed(
        title=f"📸 New Instagram Post from {user_data.get('full_name', username)}",
        url=f"https://www.instagram.com/p/{post.get('shortcode')}/",
        color=0xE4405F,
        timestamp=datetime.fromtimestamp(post.get('taken_at_timestamp', datetime.now().timestamp()))
    )
    
    if user_data.get('profile_pic_url_hd'):
        embed.set_thumbnail(url=user_data['profile_pic_url_hd'])
    
    if post.get('thumbnail_src'):
        embed.set_image(url=post['thumbnail_src'])
    elif post.get('display_url'):
        embed.set_image(url=post['display_url'])
    
    caption_edges = post.get('edge_media_to_caption', {}).get('edges', [])
    if caption_edges:
        caption_text = caption_edges[0]['node']['text']
        if len(caption_text) > 500:
            caption_text = caption_text[:500] + "..."
        embed.add_field(name="Caption", value=caption_text, inline=False)
    
    if post.get('edge_media_preview_like', {}).get('count'):
        embed.add_field(name="❤️ Likes", value=f"{post['edge_media_preview_like']['count']:,}", inline=True)
    
    if post.get('edge_media_to_comment', {}).get('count'):
        embed.add_field(name="💬 Comments", value=f"{post['edge_media_to_comment']['count']:,}", inline=True)
    
    if post.get('is_video'):
        embed.add_field(name="Type", value="Video", inline=True)
        if post.get('video_view_count'):
            embed.add_field(name="👁️ Views", value=f"{post['video_view_count']:,}", inline=True)
    else:
        embed.add_field(name="Type", value="Photo", inline=True)
    
    embed.set_footer(text=f"@{username} • Instagram")
    await channel.send(embed=embed)

@bot.command(name="addinsta")
async def add_instagram(ctx, username: str, channel: discord.TextChannel = None):
    target_channel = channel or ctx.channel
    
    if username in monitor.accounts:
        await ctx.send(f"@{username} already monitored")
        return
    
    user_data = await fetch_instagram_data(username)
    if not user_data:
        await ctx.send("Account not found")
        return
    
    monitor.accounts[username] = {
        'channel_id': str(target_channel.id),
        'added_by': str(ctx.author.id),
        'added_at': datetime.now().isoformat()
    }
    monitor.save_accounts()
    
    posts = user_data.get('edge_owner_to_timeline_media', {}).get('edges', [])
    if posts:
        monitor.last_posts[username] = posts[0]['node']['id']
        monitor.save_last_posts()
    
    embed = Embed(
        title="✅ Instagram Account Added",
        description=f"Now monitoring **@{username}**",
        color=0x00ff00
    )
    embed.add_field(name="Channel", value=target_channel.mention)
    embed.add_field(name="Posts", value=user_data.get('edge_owner_to_timeline_media', {}).get('count', 0))
    embed.add_field(name="Followers", value=user_data.get('edge_followed_by', {}).get('count', 0))
    
    if user_data.get('profile_pic_url_hd'):
        embed.set_thumbnail(url=user_data['profile_pic_url_hd'])
    
    await ctx.send(embed=embed)
    
    if not check_instagram.is_running():
        check_instagram.start()

@bot.command(name="removeinsta")
async def remove_instagram(ctx, username: str):
    if username not in monitor.accounts:
        await ctx.send(f"@{username} not monitored")
        return
    
    del monitor.accounts[username]
    monitor.save_accounts()
    
    if username in monitor.last_posts:
        del monitor.last_posts[username]
        monitor.save_last_posts()
    
    await ctx.send(f"✅ Removed @{username}")

@bot.command(name="listinsta")
async def list_instagram(ctx):
    if not monitor.accounts:
        await ctx.send("No accounts monitored")
        return
    
    embed = Embed(title="📋 Monitored Accounts", color=0xE4405F)
    
    for username, data in monitor.accounts.items():
        channel = bot.get_channel(int(data['channel_id']))
        channel_name = channel.mention if channel else "Unknown"
        embed.add_field(
            name=f"@{username}",
            value=f"Channel: {channel_name}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name="checknow")
async def check_now(ctx):
    await ctx.send("Checking accounts...")
    if check_instagram.is_running():
        check_instagram.restart()
    else:
        await check_instagram()
    await ctx.send("Check complete")

@bot.command(name="instastats")
async def insta_stats(ctx, username: str):
    user_data = await fetch_instagram_data(username)
    if not user_data:
        await ctx.send("Account not found")
        return
    
    embed = Embed(title=f"📊 @{username}", color=0xE4405F)
    
    if user_data.get('profile_pic_url_hd'):
        embed.set_thumbnail(url=user_data['profile_pic_url_hd'])
    
    embed.add_field(name="Full Name", value=user_data.get('full_name', 'N/A'))
    embed.add_field(name="Followers", value=f"{user_data.get('edge_followed_by', {}).get('count', 0):,}")
    embed.add_field(name="Following", value=f"{user_data.get('edge_follow', {}).get('count', 0):,}")
    embed.add_field(name="Posts", value=f"{user_data.get('edge_owner_to_timeline_media', {}).get('count', 0):,}")
    
    if user_data.get('biography'):
        bio = user_data['biography'][:200] + "..." if len(user_data['biography']) > 200 else user_data['biography']
        embed.add_field(name="Bio", value=bio, inline=False)
    
    embed.add_field(name="Private", value="Yes" if user_data.get('is_private') else "No")
    embed.add_field(name="Verified", value="Yes" if user_data.get('is_verified') else "No")
    
    await ctx.send(embed=embed)

@bot.command(name="testpost")
async def test_post(ctx, username: str):
    user_data = await fetch_instagram_data(username)
    if not user_data:
        await ctx.send("Account not found")
        return
    
    posts = user_data.get('edge_owner_to_timeline_media', {}).get('edges', [])
    if not posts:
        await ctx.send("No posts found")
        return
    
    latest_post = posts[0]['node']
    await send_notification(username, latest_post, user_data, {'channel_id': str(ctx.channel.id)})
    await ctx.send("Test notification sent")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing: {error.param.name}")

if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("DISCORD_TOKEN missing")
        exit()
    bot.run(token)
