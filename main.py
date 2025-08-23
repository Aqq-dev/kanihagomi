import os
import json
import io
import threading
from functools import wraps

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput
import aiohttp
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# --- 環境変数ロード ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if DISCORD_TOKEN is None:
    raise ValueError("⚠️ DISCORD_BOT_TOKEN が環境変数に設定されていません")

# --- Flask アプリ ---
app = Flask(__name__)

# --- Discord Bot ---
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 管理者チェックデコレータ ---
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

# --- Discord API リクエスト関数 ---
def discord_request(method: str, endpoint: str, data: str | None = None):
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"https://discord.com/api/v10{endpoint}"
    return requests.request(method, url, headers=headers, data=data)

# --------------------
# --- Discord コマンド ---
# --------------------

# --- role-add ---
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

# --- category-copy ---
@bot.tree.command(name="category-copy", description="指定したカテゴリをコピーします")
@app_commands.describe(category="コピーするカテゴリ")
async def category_copy_command(interaction: discord.Interaction, category: discord.CategoryChannel):
    guild_id = str(interaction.guild.id)
    source_category_id = str(category.id)

    # 元カテゴリ情報を取得
    src_res = discord_request("GET", f"/channels/{source_category_id}")
    if src_res.status_code != 200:
        await interaction.response.send_message(f"カテゴリ情報取得エラー: {src_res.text}", ephemeral=True)
        return

    src = src_res.json()
    if int(src.get("type", -1)) != 4:
        await interaction.response.send_message("指定したチャンネルはカテゴリではありません。", ephemeral=True)
        return

    payload = {
        "name": f"{src.get('name', 'category')} (copy)",
        "type": 4,
        "permission_overwrites": src.get("permission_overwrites", []),
    }

    create_res = discord_request("POST", f"/guilds/{guild_id}/channels", data=json.dumps(payload))
    if create_res.status_code not in (200, 201):
        await interaction.response.send_message(f"カテゴリ作成エラー: {create_res.text}", ephemeral=True)
        return

    created = create_res.json()
    await interaction.response.send_message(f"✅ カテゴリをコピーしました: {created.get('name')} ({created.get('id')})", ephemeral=True)

# --- ban ---
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

# --- kick ---
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

# --- embed ---
class EmbedModal(discord.ui.Modal, title="埋め込みメッセージ作成"):
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

# --- verify ---
class VerifyButton(discord.ui.Button):
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
        if role in member.roles:
            await interaction.response.send_message("あなたはすでに認証しています。", ephemeral=True)
        else:
            await member.add_roles(role)
            await interaction.response.send_message("認証が完了しました！", ephemeral=True)

class VerifyView(discord.ui.View):
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

# --- 起動イベント ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ ログインしました: {bot.user}")

# --- Bot 起動関数 ---
def run_bot():
    bot.run(DISCORD_TOKEN)

# --- Flask サーバー起動 ---
if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
