import os
import json
import io
from typing import Any, Dict
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
API_BASE = "https://discord.com/api/v10"

# --- Flask アプリ ---
app = Flask(__name__)

def discord_request(method: str, endpoint: str, data: str | None = None):
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"{API_BASE}{endpoint}"
    return requests.request(method, url, headers=headers, data=data)

@app.route("/")
def index():
    return jsonify({"ok": True, "message": "Flask Discord Category Copier is running"})

@app.route("/category-copy", methods=["POST"])
def category_copy():
    data = request.json or {}

    guild_id = str(data.get("guild_id", "")).strip()
    source_category_id = str(data.get("source_category_id", "")).strip()
    new_category_name = data.get("new_category_name")
    position = data.get("position")

    if not guild_id or not source_category_id:
        return jsonify({"ok": False, "error": "guild_id と source_category_id は必須です"}), 400

    # 1) 元カテゴリ情報を取得
    src_res = discord_request("GET", f"/channels/{source_category_id}")
    if src_res.status_code != 200:
        try:
            err = src_res.json()
        except Exception:
            err = {"message": src_res.text}
        return jsonify({"ok": False, "step": "fetch_source", "status": src_res.status_code, "error": err}), 400

    src = src_res.json()

    if int(src.get("type", -1)) != 4:
        return jsonify({"ok": False, "error": "source_category_id はカテゴリ(type=4)ではありません"}), 400

    # 2) 新しいカテゴリの作成
    payload: Dict[str, Any] = {
        "name": new_category_name or f"{src.get('name', 'category')} (copy)",
        "type": 4,
        "permission_overwrites": src.get("permission_overwrites", []),
    }
    if isinstance(position, int):
        payload["position"] = position

    create_res = discord_request("POST", f"/guilds/{guild_id}/channels", data=json.dumps(payload))
    if create_res.status_code not in (200, 201):
        try:
            err2 = create_res.json()
        except Exception:
            err2 = {"message": create_res.text}
        return jsonify({"ok": False, "step": "create_category", "status": create_res.status_code, "error": err2}), 400

    created = create_res.json()

    return jsonify({
        "ok": True,
        "guild_id": guild_id,
        "source_category_id": source_category_id,
        "created_category": {
            "id": created.get("id"),
            "name": created.get("name"),
            "type": created.get("type"),
            "position": created.get("position"),
        }
    }), 201

# --- Discord Bot ---
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# 管理者チェックデコレータ
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
        await interaction.response.send_message(
            f"{user.mention} に {role.name} ロールを付与しました。", ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message("ロールの付与に失敗しました。", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"エラー: {e}", ephemeral=True)

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
    title_input = discord.ui.TextInput(label="タイトル", placeholder="埋め込みに表示されるタイトル", max_length=256, required=False)
    description_input = discord.ui.TextInput(label="説明", style=discord.TextStyle.paragraph, placeholder="埋め込みに表示される説明", max_length=2000)
    image_url_input = discord.ui.TextInput(label="画像", placeholder="埋め込みに表示される画像のURL", max_length=1000, required=False)

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

# --- emoji-copy ---
class EmojiCopyModal(Modal, title="絵文字IDを入力"):
    emoji_id = TextInput(label="絵文字ID", placeholder="例: 123456789012345678", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        emoji_id = self.emoji_id.value.strip()
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("このコマンドはサーバー内で使用してください。", ephemeral=True)
            return
        try:
            emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.gif"
            async with aiohttp.ClientSession() as session:
                async with session.get(emoji_url) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                    else:
                        emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.png"
                        async with session.get(emoji_url) as resp:
                            if resp.status != 200:
                                raise ValueError("無効な絵文字IDか、絵文字が存在しません。")
                            image_data = await resp.read()
            image_file = io.BytesIO(image_data)
            new_emoji = await guild.create_custom_emoji(name="cloned_emoji", image=image_file.getvalue())
            await interaction.response.send_message(f"絵文字 {new_emoji} が追加されました！", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"絵文字の追加中にエラーが発生しました: {e}", ephemeral=True)
        except ValueError as e:
            await interaction.response.send_message(f"エラー: {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"エラーが発生しました: {e}", ephemeral=True)

@bot.tree.command(name="emoji-copy", description="絵文字IDを使って絵文字をコピーします。")
async def emoji_copy(interaction: discord.Interaction):
    modal = EmojiCopyModal()
    await interaction.response.send_modal(modal)

# --- trackrecord ---
class RecordModal(discord.ui.Modal, title="🌟 実績記入"):
    product = discord.ui.TextInput(label="商品名", placeholder="例)○○○○")
    rating = discord.ui.TextInput(label="評価", placeholder="1~5の中で選んでください。", required=True)
    comment = discord.ui.TextInput(label="感想", placeholder="例)迅速な対応ありがとうございました。", style=discord.TextStyle.paragraph, required=True)
    quantity = discord.ui.TextInput(label="個数", placeholder="購入した個数", required=True)

    def __init__(self, record_channel: discord.TextChannel):
        super().__init__()
        self.record_channel = record_channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating = int(self.rating.value)
            quantity = int(self.quantity.value)
            if not (1 <= rating <= 5):
                raise ValueError("評価は1〜5の範囲で入力してください")
            if quantity < 1 or quantity > 999999:
                raise ValueError("個数は1以上または999999以下で入力してください")
        except ValueError as e:
            await interaction.response.send_message(f"{e}", ephemeral=True)
            return

        stars = "★" * rating + "☆" * (5 - rating)
        embed = discord.Embed(title="🌟 実績報告", color=discord.Color.blue())
        embed.add_field(name="👤【記入者】", value=interaction.user.mention, inline=False)
        embed.add_field(name="💎【買ったもの】", value=f'{self.product.value}', inline=False)
        embed.add_field(name="⭐【評価】", value=f"__{stars}__", inline=False)
        embed.add_field(name="💬【感想】", value=f'{self.comment.value}', inline=False)
        embed.add_field(name="🛍️【個数】", value=f'{quantity}個', inline=False)
        embed.set_footer(text="Made by @aqq_dev")
        embed.set_thumbnail(url=interaction.user.avatar.url)

        await self.record_channel.send(embed=embed)
        await interaction.response.send_message("実績記入ありがとうございます！", ephemeral=True)

class RecordView(discord.ui.View):
    def __init__(self, record_channel: discord.TextChannel):
        super().__init__()
        self.record_channel = record_channel

    @discord.ui.button(label="📝 実績を記入", style=discord.ButtonStyle.green)
    async def record_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RecordModal(self.record_channel))

@bot.tree.command(name="trackrecord", description="実績記入パネルを設置します。")
@app_commands.describe(channel="実績を記録するチャンネル")
async def record(interaction: discord.Interaction, channel: discord.TextChannel):
    if interaction.user.guild_permissions.administrator:
        embed = discord.Embed(title="実績記入パネル", description="下のボタンを押して実績を記入してください。", color=discord.Color.blue())
        view = RecordView(channel)
        await interaction.channel.send(embed=embed, view=view)
        if not interaction.response.is_done():
            await interaction.response.send_message(f"実績記入パネルを {interaction.channel.mention} に設置しました！", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message("このコマンドは管理者のみ実行できます。", ephemeral=True)

# --- avatar ---
@bot.tree.command(name="avatar", description="ユーザーアバターを表示します。")
async def avatar(interaction: discord.Interaction, user: discord.User):
    avatar_url = user.avatar.url
    embed = discord.Embed(description=f"## {user.mention} さんのアバター", color=discord.Color.blue())
    embed.set_image(url=avatar_url)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- 起動処理 ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    for guild in bot.guilds:
        for role in guild.roles:
            bot.add_view(VerifyView(role.id))
    print(f"✅ ログインしました: {bot.user}")

# --- 実行 ---
if __name__ == "__main__":
    if DISCORD_TOKEN is None:
        raise ValueError("⚠️ DISCORD_BOT_TOKEN が環境変数に設定されていません")

    # Discord Bot 起動（非同期）
    import threading
    def run_bot():
        bot.run(DISCORD_TOKEN)

    t = threading.Thread(target=run_bot)
    t.start()

    # Flask サーバー起動
    port = int(os.getenv("PORT", 5000))

    app.run(host="0.0.0.0", port=port, debug=True)
