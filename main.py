import discord
import instaloader
from discord.ext import tasks
from datetime import datetime

client = discord.Client()

# List of Instagram usernames to monitor
creators = ['creator1', 'creator2', 'creator3']

def get_latest_reels(usernames):
    loader = instaloader.Instaloader()
    reels = []
    for username in usernames:
        profile = instaloader.Profile.from_username(loader.context, username)
        for post in profile.get_posts():
            if post.is_video:  # Check if the post is a video (Reel)
                post_time = datetime.fromtimestamp(post.date_utc)
                reels.append({
                    "username": username,
                    "url": post.url,
                    "timestamp": post_time
                })
    return reels

async def send_reel_to_discord(reels):
    channel = client.get_channel(YOUR_CHANNEL_ID)  # Replace with your channel ID
    for reel in reels:
        await channel.send(f"New Reel from {reel['username']}! {reel['url']}")

@tasks.loop(minutes=10)  # Checks every 10 minutes
async def check_for_new_reels():
    new_reels = get_latest_reels(creators)  # Fetch new Reels
    await send_reel_to_discord(new_reels)

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    check_for_new_reels.start()

client.run('YOUR_DISCORD_BOT_TOKEN')  # Replace with your bot token
