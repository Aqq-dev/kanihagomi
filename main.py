import os
import json
import threading
from functools import wraps
from datetime import datetime, timedelta, timezone
from datetime import datetime, timezone, timedelta
from datetime import timedelta
from itertools import cycle
import asyncio
import aiohttp

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Modal, TextInput, View, Button, Select

import requests
from flask import Flask
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if DISCORD_TOKEN is None:
    raise ValueError("⚠️ DISCORD_BOT_TOKEN が環境変数に設定されていません")

app = Flask(__name__)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


INTERVAL = 90 * 60  

icon_links = [
    "https://i.postimg.cc/1XW16Zvb/863f5eb4a72ae8ad45ef503f5efdc088.jpg",
    "https://i.postimg.cc/wj1gX782/a1c5ff8448717f42393e5ede5e103824.jpg",
    "https://i.postimg.cc/tCRT8qWQ/bbd5572bd5b9d9bdbf717dc4f4c4a6db.jpg",
    "https://i.postimg.cc/zfFv4syc/7b899e228e3cd46dc4cac922dab3e4fe.jpg"
]

icons = cycle(icon_links)

# ---------------- Admin Check ----------------
def is_admin():
    def decorator(func):
        @wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message(
                    "このコマンドは管理者のみ実行できます。", ephemeral=True
                )
                return
            return await func(interaction, *args, **kwargs)
        return wrapper
    return decorator

#vend info
LOG_CHANNEL_ID = 1408684167318863883
GUILD_ID = 1371091483611893790

PRODUCTS = {
    "文字化け作れるサイト": "https://lingojam.com/GlitchTextGenerator",
    "emoji大量サイト(ダウンロード可能)": "https://discords.com/emoji-list",
    "Gmail無限作成サイト": "https://www.gmailnator.com/",
    "YouTubeプレミアムアカウント無限作成方法": "https://ytpremiumforfreebykanishop.pages.dev/"
}

# ---------------- Discord API Request ----------------
def discord_request(method: str, endpoint: str, data: str | None = None):
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"https://discord.com/api/v10{endpoint}"
    return requests.request(method, url, headers=headers, data=data)


# ---------------- Role Add ----------------
@bot.tree.command(name="role-add", description="指定したユーザーに指定したロールを付与します")
@app_commands.describe(user="ロールを付与するユーザー", role="付与するロール")
async def role_add(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message("「ロールの管理」権限が必要です。", ephemeral=True)
        return
    if role >= interaction.guild.me.top_role:
        await interaction.response.send_message("そのロールは付与できません。", ephemeral=True)
        return
    try:
        await user.add_roles(role)
        await interaction.response.send_message(f"{user.mention} に {role.name} ロールを付与しました。", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("ロールの付与に失敗しました。", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"エラー: {e}", ephemeral=True)


# ---------------- Category Copy ----------------
@bot.tree.command(name="category-copy", description="指定したカテゴリをコピーします")
@app_commands.describe(category="コピーするカテゴリ")
async def category_copy_command(interaction: discord.Interaction, category: discord.CategoryChannel):
    try:
        await interaction.response.defer(ephemeral=True)
    except (discord.errors.NotFound, discord.errors.HTTPException):
        pass

    guild_id = str(interaction.guild.id)
    source_category_id = str(category.id)

    src_res = discord_request("GET", f"/channels/{source_category_id}")
    if src_res.status_code != 200:
        await interaction.followup.send(f"カテゴリ情報取得エラー: {src_res.text}", ephemeral=True)
        return
    src = src_res.json()
    if int(src.get("type", -1)) != 4:
        await interaction.followup.send("指定したチャンネルはカテゴリではありません。", ephemeral=True)
        return

    copy_name = f"{src.get('name', 'category')} (copy)"

    guild_channels_res = discord_request("GET", f"/guilds/{guild_id}/channels")
    if guild_channels_res.status_code != 200:
        await interaction.followup.send(f"サーバーチャンネル取得エラー: {guild_channels_res.text}", ephemeral=True)
        return
    guild_channels = guild_channels_res.json()
    if any(ch.get("type") == 4 and ch.get("name") == copy_name for ch in guild_channels):
        embed = discord.Embed(title="⚠️ コピー中止", color=discord.Color.red())
        embed.add_field(name="理由", value=f"同名のコピーカテゴリ「{copy_name}」が既に存在します。", inline=False)
        embed.set_footer(text=f"実行者: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    payload = {
        "name": copy_name,
        "type": 4,
        "permission_overwrites": src.get("permission_overwrites", []),
    }
    create_res = discord_request("POST", f"/guilds/{guild_id}/channels", data=json.dumps(payload))
    if create_res.status_code not in (200, 201):
        await interaction.followup.send(f"カテゴリ作成エラー: {create_res.text}", ephemeral=True)
        return
    created = create_res.json()

    embed = discord.Embed(title="✅ カテゴリコピー成功", color=discord.Color.green())
    embed.add_field(name="元カテゴリ名", value=src.get("name"), inline=True)
    embed.add_field(name="コピーカテゴリ名", value=created.get("name"), inline=True)
    embed.add_field(name="コピーカテゴリID", value=created.get("id"), inline=False)
    embed.set_footer(text=f"作成者: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------- Ban/Kick ----------------
@bot.tree.command(name="ban", description="指定したユーザーをBANします（管理者限定）")
@is_admin()
@app_commands.describe(user="BANするユーザー", reason="BANの理由（任意）")
async def ban_user(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    try:
        await user.ban(reason=reason)
        msg = f"{user.mention} をBANしました。"
        if reason:
            msg += f" 理由：{reason}"
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"エラー: {e}", ephemeral=True)


@bot.tree.command(name="kick", description="指定したユーザーをキックします（管理者限定）")
@is_admin()
@app_commands.describe(user="キックするユーザー", reason="キックの理由（任意）")
async def kick_user(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    try:
        await user.kick(reason=reason)
        msg = f"{user.mention} をキックしました。"
        if reason:
            msg += f" 理由：{reason}"
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"エラー: {e}", ephemeral=True)


# ---------------- Embed Modal ----------------
class EmbedModal(Modal, title="埋め込みメッセージ作成"):
    title_input = TextInput(label="タイトル", placeholder="埋め込みに表示されるタイトル", max_length=256, required=False)
    description_input = TextInput(label="説明", style=discord.TextStyle.paragraph, placeholder="埋め込みに表示される説明", max_length=2000)
    image_url_input = TextInput(label="画像", placeholder="埋め込みに表示される画像のURL", max_length=1000, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title=self.title_input.value, description=self.description_input.value, color=discord.Color.blue())
        if self.image_url_input.value:
            embed.set_image(url=self.image_url_input.value)
        embed.set_footer(text=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message("埋め込みメッセージを送信しました！", ephemeral=True)
        await interaction.channel.send(embed=embed)


@bot.tree.command(name="embed", description="埋め込みメッセージを作成します。")
async def embed_command(interaction: discord.Interaction):
    await interaction.response.send_modal(EmbedModal())


# ---------------- Verify Button ----------------
class VerifyButton(Button):
    def __init__(self, role_id: int):
        super().__init__(style=discord.ButtonStyle.success, label="✅ 認証/Verify", custom_id=f"verify_{role_id}")
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user
        role = guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("ロールが見つかりません。", ephemeral=True)
            return
        if role >= guild.me.top_role:
            await interaction.response.send_message("Botの権限が不足しています。", ephemeral=True)
            return
        if role in member.roles:
            await interaction.response.send_message("すでに認証済みです。", ephemeral=True)
        else:
            try:
                await member.add_roles(role)
                await interaction.response.send_message("認証が完了しました！", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("権限が不足しており、ロールを付与できません。", ephemeral=True)


class VerifyView(View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.add_item(VerifyButton(role_id))


@bot.tree.command(name="verify", description="認証パネルを作成します")
@app_commands.describe(role="付与するロール", description="認証パネルの説明", image_url="埋め込む画像URL")
async def verify(interaction: discord.Interaction, role: discord.Role, description: str, image_url: str = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("このコマンドを使用するには管理者権限が必要です。", ephemeral=True)
        return
    embed = discord.Embed(title="認証パネル", description=description, color=discord.Color.green())
    if image_url:
        embed.set_image(url=image_url)
    view = VerifyView(role.id)
    await interaction.response.send_message(embed=embed, view=view)
    bot.add_view(view)


# ---------------- Terms Verify ----------------
class TermsVerifyButton(Button):
    def __init__(self, role_id: int):
        super().__init__(label="同意", style=discord.ButtonStyle.success, custom_id=f"terms_verify_button_{role_id}")
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        # Interaction を ACK しておく
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        role = discord.utils.get(interaction.guild.roles, id=self.role_id)
        user = interaction.user

        if not role:
            await interaction.followup.send("ロールが見つかりませんでした。", ephemeral=True)
            return

        if role >= interaction.guild.me.top_role:
            await interaction.followup.send("Botの権限が不足しています。", ephemeral=True)
            return

        if role in user.roles:
            await interaction.followup.send("すでにロールが付与されています。", ephemeral=True)
            return

        try:
            await user.add_roles(role)
            await interaction.followup.send(f"{role.mention} ロールが付与されました！", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("Botの権限が不足しています。", ephemeral=True)


async def send_safe(interaction: discord.Interaction, content: str):
    """
    Interaction が無効になっても followup で送れるようにする
    """
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(content, ephemeral=True)
        else:
            await interaction.followup.send(content, ephemeral=True)
    except discord.errors.NotFound:
        print(f"Interaction 無効: {content}")


class TermsVerifyView(View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.add_item(TermsVerifyButton(role_id))


class TermsModal(Modal, title="利用規約入力"):
    def __init__(self, role_id: int):
        super().__init__()
        self.role_id = role_id
        self.terms = TextInput(label="利用規約内容", style=discord.TextStyle.paragraph, required=True, max_length=2000)
        self.add_item(self.terms)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title=f"{interaction.guild.name} 利用規約", description=self.terms.value, color=discord.Color.random())
        view = TermsVerifyView(self.role_id)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("利用規約同意を送信しました。", ephemeral=True)


@bot.tree.command(name="terms-verify-button", description="利用規約ボタンを表示")
@app_commands.describe(role="同意時に付与するロール")
async def termsverify_button(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "このコマンドを使用するには管理者権限が必要です。", ephemeral=True
        )
        return

    try:
        # defer 不要、直接モーダル送信
        await interaction.response.send_modal(TermsModal(role.id))
    except discord.errors.HTTPException as e:
        await interaction.followup.send(f"モーダル送信失敗: {e}", ephemeral=True)

#vend
class QuantityModal(Modal, title="購入フォーム"):
    quantity = TextInput(label="個数を入力してください (1のみ)", placeholder="1", max_length=1)

    def __init__(self, product_name: str):
        super().__init__(custom_id=f"modal_{product_name}")
        self.product_name = product_name

    async def on_submit(self, interaction: discord.Interaction):
        qty = self.quantity.value
        if qty != "1":
            await interaction.response.send_message("無料自販機は1個までしか購入できません。", ephemeral=True)
            return

        JST = timezone(timedelta(hours=9))
        now = datetime.now(JST).strftime("%y/%m/%d %H:%M:%S(JST)")

        await interaction.response.send_message("購入情報をDMに送信しました。", ephemeral=True)

        # DMに商品リンクと埋め込み
        try:
            await interaction.user.send(f"こちらが商品リンクです:\n{PRODUCTS[self.product_name]}")

            embed = discord.Embed(title="✅ 購入が完了しました", color=discord.Color.green())
            embed.add_field(name="購入日", value=f"```{now}```", inline=False)
            embed.add_field(name="購入サーバー", value=f"```{interaction.guild.name}\n({interaction.guild.id})```", inline=False)
            embed.add_field(name="商品名", value=f"```{self.product_name}```", inline=False)
            embed.add_field(name="購入数", value="```1個```", inline=True)
            embed.add_field(name="支払金額", value="```0円```", inline=True)
            await interaction.user.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send("DMを送信できませんでした。DMを開放してください。", ephemeral=True)

        # ログチャンネルに送信
        guild = interaction.guild or bot.get_guild(GUILD_ID)
        if guild:
            log_channel = guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                log_embed = discord.Embed(title="📝 購入実績", color=discord.Color.orange())
                log_embed.add_field(name="購入者", value=interaction.user.mention, inline=False)
                log_embed.add_field(name="個数", value="```1個```", inline=True)
                log_embed.add_field(name="商品", value=f"```{self.product_name}```", inline=False)
                await log_channel.send(embed=log_embed)

class ProductSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=name, description="0円", value=name)
            for name in PRODUCTS.keys()
        ]
        super().__init__(placeholder="商品を選択してください", options=options, custom_id="product_select")

    async def callback(self, interaction: discord.Interaction):
        modal = QuantityModal(self.values[0])
        await interaction.response.send_modal(modal)

class ProductView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ProductSelect())

@bot.tree.command(name="freevend-1", description="無料自販機を表示します")
async def freevend(interaction: discord.Interaction):
    embed = discord.Embed(title="🎁 無料自販機", description="以下から商品を選択してください", color=discord.Color.blurple())
    for name in PRODUCTS.keys():
        embed.add_field(name=name, value="```0円```", inline=False)
    await interaction.response.send_message(embed=embed, view=ProductView())

#timeout
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.author.guild_permissions.administrator:
        return

    JST = timezone(timedelta(hours=9))
    
    # 招待リンクチェック
    invite_substrings = (
        "https://discord.gg/",
        "https://discord.com/invite/",
        "https://discordapp.com/invite/",
        "discordapp.com/invite/",
        "discord.gg/",
        "discord.gg/invite/"
    )
    
    if any(sub in message.content for sub in invite_substrings):
        try:
            await message.delete()
            until_time = datetime.now(JST) + timedelta(minutes=10)
            # キーワードではなく位置引数で渡す
            await message.author.timeout(until_time, "招待リンク送信")
            embed = discord.Embed(
                title="警告",
                description=f"管理者ではないユーザーが Discord の招待リンクを送信しました。\n{message.author.mention} を 10 分間タイムアウトします。",
                color=discord.Color.red()
            )
            await message.channel.send(embed=embed)
        except (discord.NotFound, discord.HTTPException):
            pass
        return

    # @everyone/@here チェック
    if message.mention_everyone:
        try:
            await message.delete()
            until_time = datetime.now(JST) + timedelta(minutes=10)
            await message.author.timeout(until_time, "@everyone/@hereメンション送信")
            embed = discord.Embed(
                title="警告",
                description=f"管理者ではないユーザーが @everyone または @here を送信しました。\n{message.author.mention} を 10 分間タイムアウトします。",
                color=discord.Color.red()
            )
            await message.channel.send(embed=embed)
        except (discord.NotFound, discord.HTTPException):
            pass
#aa
async def change_icon_task():
    await bot.wait_until_ready()
    async with aiohttp.ClientSession() as session:
        while not bot.is_closed():
            url = next(icons)
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        img = await resp.read()
                        await bot.user.edit(avatar=img)
                        print(f"✅ アイコンを変更しました → {url}")
            except Exception as e:
                print(f"⚠️ アイコン変更エラー: {e}")
            await asyncio.sleep(INTERVAL)


# --- Botクラスを拡張してsetup_hookを使う ---
class MyBot(commands.Bot):
    async def setup_hook(self):
        # アイコン変更タスクを登録
        self.loop.create_task(change_icon_task())

# ---------------- Status Update Task ----------------
@tasks.loop(seconds=5)
async def update_status():
    total_members = sum(guild.member_count for guild in bot.guilds)
    latency_ms = round(bot.latency * 1000)
    status_text = f"{latency_ms}ms Ping | {total_members} Users"
    activity = discord.Activity(name=status_text, type=discord.ActivityType.watching)
    await bot.change_presence(status=discord.Status.idle, activity=activity)

# ---------------- On Ready ----------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    for guild in bot.guilds:
        for role in guild.roles:
            bot.add_view(VerifyView(role.id))
            bot.add_view(TermsVerifyView(role.id))
            bot.add_view(ProductView())
    update_status.start()
    print(f"✅ ログインしました: {bot.user}")


def run_bot():
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
