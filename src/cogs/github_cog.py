import discord
from discord import app_commands
from discord.ext import commands
import logging

from src.utils.github_utils import (
    extract_github_username,
    extract_github_repo,
    format_date,
    format_number,
    github_request,
)

logger = logging.getLogger(__name__)


class GitHubCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="github_user", description="Get GitHub user profile information")
    @app_commands.describe(username="GitHub username or profile URL")
    async def github_user(self, interaction: discord.Interaction, username: str):
        try:
            await interaction.response.defer()
            username = extract_github_username(username)
            data = await github_request(self.bot, f"https://api.github.com/users/{username}")

            if data == "rate_limited":
                await interaction.followup.send("❌ GitHub API rate limit exceeded. Please try again later.")
                return
            elif data == "not_found":
                await interaction.followup.send(f"❌ User **{username}** not found on GitHub")
                return
            elif not data:
                await interaction.followup.send(f"❌ Failed to fetch data for **{username}**")
                return

            embed = discord.Embed(
                title=f"{data.get('name', username)}'s GitHub Profile",
                url=data['html_url'],
                description=data.get('bio', 'No bio available'),
                color=0x238636,
            )
            embed.set_thumbnail(url=data['avatar_url'])
            embed.add_field(name="👤 Username", value=f"[{username}]({data['html_url']})", inline=True)
            embed.add_field(name="📦 Public Repos", value=format_number(data.get('public_repos', 0)), inline=True)
            embed.add_field(name="👥 Followers", value=format_number(data.get('followers', 0)), inline=True)
            embed.add_field(name="👤 Following", value=format_number(data.get('following', 0)), inline=True)
            embed.add_field(name="📍 Location", value=data.get('location', 'N/A'), inline=True)
            embed.add_field(name="🏢 Company", value=data.get('company', 'N/A'), inline=True)
            embed.add_field(name="📅 Joined", value=format_date(data.get('created_at')), inline=True)

            socials = []
            if data.get('blog'):
                socials.append(f"🌐 [Website]({data['blog']})")
            if data.get('twitter_username'):
                socials.append(f"🐦 [Twitter](https://twitter.com/{data['twitter_username']})")
            if socials:
                embed.add_field(name="🔗 Links", value=" | ".join(socials), inline=False)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"github_user command error: {e}")
            try:
                await interaction.followup.send("❌ An error occurred while fetching user data.")
            except:
                pass

    @app_commands.command(name="github_repo", description="Get GitHub repository details")
    @app_commands.describe(repo="owner/repo or repository URL")
    async def github_repo(self, interaction: discord.Interaction, repo: str):
        try:
            await interaction.response.defer()
            parsed = extract_github_repo(repo)
            if not parsed:
                await interaction.followup.send("❌ Please provide a valid repository in the form `owner/repo` or a GitHub URL.")
                return
            owner, name = parsed
            data = await github_request(self.bot, f"https://api.github.com/repos/{owner}/{name}")

            if data == "rate_limited":
                await interaction.followup.send("❌ GitHub API rate limit exceeded. Please try again later.")
                return
            elif data == "not_found":
                await interaction.followup.send(f"❌ Repository **{owner}/{name}** not found on GitHub")
                return
            elif not data:
                await interaction.followup.send(f"❌ Failed to fetch data for **{owner}/{name}**")
                return

            description = data.get('description') or 'No description provided.'
            embed = discord.Embed(
                title=f"{owner}/{name}",
                url=data.get('html_url', f"https://github.com/{owner}/{name}"),
                description=description,
                color=0x0d1117,
            )

            if data.get('owner', {}).get('avatar_url'):
                embed.set_thumbnail(url=data['owner']['avatar_url'])

            embed.add_field(name="⭐ Stars", value=format_number(data.get('stargazers_count', 0)), inline=True)
            embed.add_field(name="🍴 Forks", value=format_number(data.get('forks_count', 0)), inline=True)
            embed.add_field(name="🐛 Open Issues", value=format_number(data.get('open_issues_count', 0)), inline=True)
            embed.add_field(name="🗣️ Language", value=data.get('language', 'N/A'), inline=True)
            embed.add_field(name="📄 License", value=(data.get('license') or {}).get('name', 'N/A'), inline=True)
            embed.add_field(name="🕒 Updated", value=format_date(data.get('updated_at')), inline=True)

            links = []
            if data.get('homepage'):
                links.append(f"🌐 [Homepage]({data['homepage']})")
            links.append(f"📦 [Repo]({data.get('html_url', f'https://github.com/{owner}/{name}')})")
            embed.add_field(name="🔗 Links", value=" | ".join(links), inline=False)

            topics = data.get('topics') or []
            if topics:
                embed.add_field(name="🏷️ Topics", value=", ".join(topics[:10]), inline=False)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"github_repo command error: {e}")
            try:
                await interaction.followup.send("❌ An error occurred while fetching repository data.")
            except:
                pass

    @app_commands.command(name="github_search", description="Search for GitHub repositories by criteria")
    @app_commands.describe(query="Search query, e.g., language:python stars:>1000")
    async def github_search(self, interaction: discord.Interaction, query: str):
        try:
            await interaction.response.defer()
            search_url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=5"
            data = await github_request(self.bot, search_url)

            if data == "rate_limited":
                await interaction.followup.send("❌ GitHub API rate limit exceeded. Please try again later.")
                return
            elif not data or not data.get("items"):
                await interaction.followup.send(f"❌ No repositories found for query: **{query}**")
                return
            elif data.get("incomplete_results", False):
                logger.warning("GitHub search returned incomplete results")

            embed = discord.Embed(
                title=f"🔍 GitHub Repository Search Results",
                description=f"Query: `{query}`\nShowing top {len(data['items'])} results:",
                color=0x238636,
            )

            for i, repo in enumerate(data["items"], start=1):
                name = repo.get("name", "N/A")
                owner = repo.get("owner", {}).get("login", "N/A")
                full_name = f"{owner}/{name}"
                description = repo.get("description", "No description available.")
                if len(description) > 200:
                    description = description[:200] + "..."
                stars = format_number(repo.get("stargazers_count", 0))
                language = repo.get("language", "N/A")
                repo_url = repo.get("html_url", "")

                embed.add_field(
                    name=f"{i}. {full_name}",
                    value=f"⭐ {stars} | 🗣️ {language}\n{description}\n🔗 [View Repo]({repo_url})",
                    inline=False,
                )

            embed.set_footer(text=f"Total results: {data.get('total_count', 0)} | Powered by GitHub API")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"github_search command error: {e}")
            try:
                await interaction.followup.send("❌ An error occurred while searching repositories.")
            except:
                pass

    @app_commands.command(name="github_tree", description="Show a repository file tree (owner/repo or URL)")
    @app_commands.describe(repo="Repository (owner/repo) or GitHub URL", max_depth="Max depth to display")
    async def github_tree(self, interaction: discord.Interaction, repo: str, max_depth: int = 3):
        try:
            await interaction.response.defer()

            # CONFIG / CONSTANTS
            EMBED_COLOR = 0x000000
            MAX_PATH_LIMIT = 5000
            MAX_EMBEDS = 4
            MAX_FIELD_VALUE = 1024 - 15
            MAX_CONTENT_CHARS = min(750, MAX_FIELD_VALUE)

            branch = None
            subpath = ""

            # PARSE REPOSITORY INPUT
            from urllib.parse import urlparse

            if repo.startswith("http"):
                url_parts = urlparse(repo).path.strip("/").split("/")
                if len(url_parts) >= 2:
                    owner, name = url_parts[:2]
                    if len(url_parts) >= 4 and url_parts[2] == "tree":
                        branch = url_parts[3]
                        subpath = "/".join(url_parts[4:]) if len(url_parts) > 4 else ""
                else:
                    await interaction.followup.send("❌ Invalid GitHub URL.")
                    return
            elif "/" in repo:
                owner, name = repo.split("/")[:2]
            else:
                await interaction.followup.send("❌ Invalid repository format. Use `owner/repo` or a GitHub URL.")
                return

            # TREE
            repo_data = await github_request(self.bot, f"https://api.github.com/repos/{owner}/{name}")
            if repo_data == "not_found":
                await interaction.followup.send("❌ Repository not found.")
                return
            if repo_data == "rate_limited":
                await interaction.followup.send("❌ GitHub API rate limit exceeded. Try again later or use a token.")
                return
            if not isinstance(repo_data, dict):
                await interaction.followup.send("❌ Unexpected response from GitHub API.")
                return

            branch = branch or repo_data.get("default_branch", "main")

            tree_url = f"https://api.github.com/repos/{owner}/{name}/git/trees/{branch}?recursive=1"
            tree_data = await github_request(self.bot, tree_url)

            if tree_data == "not_found":
                await interaction.followup.send(f"❌ Branch `{branch}` or repository tree not found.")
                return
            if tree_data == "rate_limited":
                await interaction.followup.send("❌ GitHub API rate limit exceeded while fetching the tree.")
                return
            if not isinstance(tree_data, dict) or "tree" not in tree_data:
                await interaction.followup.send("❌ Failed to fetch repository tree (unexpected API response).")
                return

            all_paths = [item["path"] for item in tree_data.get("tree", []) if item.get("type") in ("blob", "tree")]

            if not all_paths:
                await interaction.followup.send(f"❌ The repository `{owner}/{name}` appears empty on branch `{branch}`.")
                return

            if len(all_paths) > MAX_PATH_LIMIT:
                await interaction.followup.send(
                    f"⚠️ **Repository Too Large:** `{owner}/{name}` has **{len(all_paths)}** files/directories, exceeding the limit of **{MAX_PATH_LIMIT}** items.\n"
                    f"Try specifying a smaller subpath, e.g. `{owner}/{name}/tree/{branch}/src`."
                )
                return

            paths = []
            if subpath:
                filtered_paths = [p for p in all_paths if p == subpath or p.startswith(subpath + "/")]
                if not filtered_paths:
                    await interaction.followup.send(f"❌ Subpath `{subpath}` not found or is a dead end.")
                    return

                if any(p.startswith(subpath + "/") for p in filtered_paths):
                    subpath_len = len(subpath) + 1
                    paths = [p[subpath_len:] for p in filtered_paths if p.startswith(subpath + "/")]
                else:
                    paths = [subpath]
            else:
                paths = all_paths

            if not paths:
                await interaction.followup.send(f"❌ No files or directories found in `{owner}/{name}/{subpath}`.")
                return

            def format_tree(paths_list, max_depth=3):
                tree_dict = {}
                for p in paths_list:
                    parts = p.split("/")
                    current = tree_dict
                    for i, part in enumerate(parts):
                        if i >= max_depth:
                            if isinstance(current, dict) and part not in current:
                                current[part] = "..."
                            break

                        if part not in current:
                            current[part] = {}

                        if current[part] != "...":
                            current = current[part]

                        if i == len(parts) - 1:
                            break

                lines = []

                def build_lines(d, prefix=""):
                    def sort_key(item):
                        key, value = item
                        is_dir = isinstance(value, dict) and value != {}
                        return (not is_dir, key.lower())

                    sorted_items = sorted(d.items(), key=sort_key)
                    for i, (key, value) in enumerate(sorted_items):
                        is_directory = isinstance(value, dict) and value != {}
                        is_truncated = value == "..."
                        is_last = (i == len(sorted_items) - 1)

                        connector = "└── " if is_last else "├── "
                        next_prefix = prefix + ("    " if is_last else "│   ")
                        suffix = "/" if is_directory or is_truncated else ""

                        lines.append(f"{prefix}{connector}{key}{suffix}")

                        if is_directory and value:
                            build_lines(value, next_prefix)

                root_name = f"📦 {owner}/{name}/tree/{branch}/{subpath}" if subpath else f"📦 {owner}/{name}/tree/{branch}"
                lines.append(root_name)
                build_lines(tree_dict)
                return lines

            tree_lines = format_tree(paths, max_depth)

            chunks = []
            current_chunk = []
            current_len = 0

            for line in tree_lines:
                if len(line) > MAX_CONTENT_CHARS:
                    line = line[:MAX_CONTENT_CHARS - 3] + "..."

                if current_len + len(line) + 1 > MAX_CONTENT_CHARS:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = []
                    current_len = 0

                current_chunk.append(line)
                current_len += len(line) + 1

            if current_chunk:
                chunks.append("\n".join(current_chunk))

            if len(chunks) > MAX_EMBEDS:
                chunks = chunks[:MAX_EMBEDS]
                trunc_msg = "\n\n… (Output truncated by embed limit)"
                if len(chunks[-1]) + len(trunc_msg) > MAX_CONTENT_CHARS:
                    available = max(0, MAX_CONTENT_CHARS - len(trunc_msg) - 3)
                    chunks[-1] = chunks[-1][:available] + "..." + trunc_msg
                else:
                    chunks[-1] = chunks[-1] + trunc_msg

            if any(len(c) + 10 > MAX_FIELD_VALUE for c in chunks):
                import io
                file_content = "\n".join(tree_lines)
                fp = io.BytesIO(file_content.encode("utf-8"))
                fp.seek(0)
                filename = f"{owner}-{name}-tree-{branch}{('-' + subpath.replace('/', '_')) if subpath else ''}.txt"
                await interaction.followup.send(
                    content=f"📁 Repository tree is large — sending as a file: `{filename}`",
                    file=discord.File(fp, filename=filename)
                )
                return

            embeds_to_send = []
            repo_url = f"https://github.com/{owner}/{name}"
            author_url = f"https://github.com/{owner}/{name}/tree/{branch}/{subpath}" if subpath else f"https://github.com/{owner}/{name}/tree/{branch}"

            total_parts = len(chunks)

            for idx, chunk in enumerate(chunks, start=1):
                embed = discord.Embed(
                    title=f"File Tree for {owner}/{name}",
                    description=f"**Branch:** `{branch}` **Path:** `/{subpath if subpath else ''}`",
                    color=EMBED_COLOR,
                    url=repo_url,
                )

                embed.set_author(
                    name=f"{owner}/{name} (branch: {branch})",
                    url=author_url,
                )

                embed.add_field(
                    name=f"Tree Structure (Max Depth: {max_depth}) - Part {idx}/{total_parts}",
                    value=f"```fix\n{chunk}\n```",
                    inline=False
                )

                embed.set_footer(
                    text=f"Requested by {interaction.user.display_name} | {len(all_paths)} total files/dirs",
                    icon_url=interaction.user.display_avatar.url
                )
                embed.timestamp = discord.utils.utcnow()
                embeds_to_send.append(embed)

            if not embeds_to_send:
                await interaction.followup.send(f"❌ No content to display for `{owner}/{name}`.")
                return

            import io, traceback

            # Send first embed
            try:
                await interaction.followup.send(embeds=[embeds_to_send[0]])
            except Exception as e:
                print("Error sending first embed:", e)
                traceback.print_exc()
                file_content = "\n".join(tree_lines)
                fp = io.BytesIO(file_content.encode("utf-8"))
                fp.seek(0)
                filename = f"{owner}-{name}-tree-{branch}{('-' + subpath.replace('/', '_')) if subpath else ''}.txt"
                await interaction.followup.send(
                    content="📁 Unable to send embeds reliably; sending full tree as a file.",
                    file=discord.File(fp, filename=filename)
                )
                return

            for i, embed in enumerate(embeds_to_send[1:], start=1):
                try:
                    await interaction.followup.send(embeds=[embed])
                except Exception as send_err:
                    # Log the error
                    print(f"Error sending embed part {i+1}:", send_err)
                    traceback.print_exc()

                    remaining_chunks = []
                    try:
                        remaining_chunks = chunks[i:]
                    except Exception:
                        remaining_chunks = ["(Could not reconstruct chunk text)"]

                    combined_text = "\n\n--- Part Break ---\n\n".join(remaining_chunks)
                    header = f"Repository tree for {owner}/{name} (branch: {branch})\nPath: /{subpath if subpath else ''}\n\n"
                    file_content = header + combined_text

                    fp = io.BytesIO(file_content.encode("utf-8"))
                    fp.seek(0)
                    filename = f"{owner}-{name}-tree-{branch}-remaining.txt"
                    await interaction.followup.send(
                        content="📁 Part of the output couldn't be sent as embeds — sending remaining parts as a single .txt file.",
                        file=discord.File(fp, filename=filename)
                    )
                    return  # done after fallback

            return

        except Exception:
            import traceback
            print(f"--- GITHUB TREE COMMAND ERROR ---")
            try:
                user = interaction.user.display_name
            except Exception:
                user = "unknown"
            print(f"Repo: {repo}, User: {user}")
            traceback.print_exc()
            print(f"---------------------------------")
            try:
                await interaction.followup.send("❌ An unexpected internal error occurred while fetching the repository tree. Check bot logs for details.")
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(GitHubCog(bot))
