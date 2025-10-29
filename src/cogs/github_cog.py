import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime, timedelta, timezone

from urllib.parse import quote_plus

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
            q = quote_plus(query, safe=":+-><=")
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

    @app_commands.command(name="github_trending", description="Show trending GitHub repositories or developers")
    @app_commands.describe(
        date_range="Time period for trending (today, this_week, this_month)",
        type="Show trending repositories or developers",
        language="Programming language filter (leave empty for ALL languages)"
    )
    @app_commands.choices(date_range=[
        app_commands.Choice(name="Today", value="today"),
        app_commands.Choice(name="This Week", value="this_week"),
        app_commands.Choice(name="This Month", value="this_month")
    ])
    @app_commands.choices(type=[
        app_commands.Choice(name="Repositories", value="repositories"),
        app_commands.Choice(name="Developers", value="developers")
    ])
    async def github_trending(
        self,
        interaction: discord.Interaction,
        date_range: str,
        type: str,
        language: str | None = None
    ):
        try:
            await interaction.response.defer()

            # Calculate date based on range
            today = datetime.now(timezone.utc)
            if date_range == "today":
                since_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                range_label = "Today"
            elif date_range == "this_week":
                since_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
                range_label = "This Week"
            elif date_range == "this_month":
                since_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
                range_label = "This Month"
            else:
                await interaction.followup.send("❌ Invalid date range selected.")
                return

            if type == "repositories":
                # Build search query for trending repositories
                query_parts = [f"created:>={since_date}"]
                if language:
                    query_parts.append(f"language:{language}")

                query = " ".join(query_parts)
                search_url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=3"

                data = await github_request(self.bot, search_url)

                if data == "rate_limited":
                    await interaction.followup.send("❌ GitHub API rate limit exceeded. Please try again later.")
                    return
                elif data == "not_found":
                    await interaction.followup.send("❌ Could not fetch trending data from GitHub.")
                    return
                elif not data or not isinstance(data, dict):
                    lang_text = f" for {language}" if language else ""
                    await interaction.followup.send(f"❌ No trending repositories found{lang_text} for {range_label.lower()}.")
                    return

                # Safely get items list
                items = data.get("items", [])
                if not items or not isinstance(items, list):
                    lang_text = f" for {language}" if language else ""
                    await interaction.followup.send(f"❌ No trending repositories found{lang_text} for {range_label.lower()}.")
                    return

                # Create embed for repositories
                lang_text = f" - {language.title()}" if language else " - All Languages"
                embed = discord.Embed(
                    title=f"🔥 Trending Repositories{lang_text}",
                    description=f"**Top {len(items)} trending repos from {range_label.lower()}**\n",
                    color=0x2F3136,
                )

                repo_entries = []
                for i, repo in enumerate(items[:3], start=1):
                    name = repo.get("name", "N/A")
                    owner = repo.get("owner", {}).get("login", "N/A")
                    full_name = f"{owner}/{name}"
                    description = repo.get("description", "No description available.")
                    if description and len(description) > 120:
                        description = description[:120] + "..."

                    stars = format_number(repo.get("stargazers_count", 0))
                    forks = format_number(repo.get("forks_count", 0))
                    # Note: open_issues_count includes both issues AND open PRs
                    open_issues_and_prs = repo.get("open_issues_count", 0)
                    repo_url = repo.get("html_url", "")

                    # Fetch all languages used in the repository
                    languages_url = f"https://api.github.com/repos/{owner}/{name}/languages"
                    lang_data = await github_request(self.bot, languages_url)

                    if lang_data and isinstance(lang_data, dict) and lang_data not in ["rate_limited", "not_found"]:
                        # Get top languages sorted by bytes
                        sorted_langs = sorted(lang_data.items(), key=lambda x: x[1], reverse=True)
                        # Take top 5 languages or all if less than 5
                        top_langs = [lang[0] for lang in sorted_langs[:5]]
                        languages_text = ", ".join(top_langs) if top_langs else "N/A"
                    else:
                        # Fallback to primary language
                        languages_text = repo.get("language", "N/A")

                    # Fetch total PRs count
                    search_prs_url = f"https://api.github.com/search/issues?q=repo:{owner}/{name}+type:pr"
                    prs_data = await github_request(self.bot, search_prs_url)

                    if prs_data and isinstance(prs_data, dict) and prs_data not in ["rate_limited", "not_found"]:
                        total_prs = prs_data.get('total_count', 0)
                        total_prs_formatted = format_number(total_prs)
                    else:
                        total_prs = 0
                        total_prs_formatted = "N/A"

                    # Fetch open PRs count to calculate actual open issues
                    search_open_prs_url = f"https://api.github.com/search/issues?q=repo:{owner}/{name}+type:pr+state:open"
                    open_prs_data = await github_request(self.bot, search_open_prs_url)

                    if open_prs_data and isinstance(open_prs_data, dict) and open_prs_data not in ["rate_limited", "not_found"]:
                        open_prs_count = open_prs_data.get('total_count', 0)
                    else:
                        open_prs_count = 0

                    # Calculate actual open issues (open_issues_count includes open PRs, so subtract them)
                    actual_open_issues = max(0, open_issues_and_prs - open_prs_count)
                    open_issues = format_number(actual_open_issues)

                    entry = (
                        f"### {i}. [{full_name}]({repo_url})\n"
                        f"> {description}\n"
                        f"> \n"
                        f"> ⭐ **{stars}** Stars  •  🍴 **{forks}** Forks  •  🔀 **{total_prs_formatted}** PRs  •  🐛 **{open_issues}** Open Issues\n"
                        f"> 🗣️ **Languages:** {languages_text}\n"
                    )
                    repo_entries.append(entry)

                # Combine all entries with separators
                separator = "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                embed.description += separator.join(repo_entries)

                total_count = data.get('total_count', 0) or 0
                embed.set_footer(text=f"Total results: {total_count:,} | Powered by GitHub API")
                await interaction.followup.send(embed=embed)

            elif type == "developers":
                # For developers, we search for users who created popular repos recently
                query_parts = [f"created:>={since_date}", "stars:>10"]  # Repos with at least 10 stars
                if language:
                    query_parts.append(f"language:{language}")

                query = " ".join(query_parts)
                search_url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=10"

                data = await github_request(self.bot, search_url)

                if data == "rate_limited":
                    await interaction.followup.send("❌ GitHub API rate limit exceeded. Please try again later.")
                    return
                elif data == "not_found":
                    await interaction.followup.send("❌ Could not fetch trending data from GitHub.")
                    return
                elif not data or not isinstance(data, dict):
                    lang_text = f" for {language}" if language else ""
                    await interaction.followup.send(f"❌ No trending developers found{lang_text} for {range_label.lower()}.")
                    return

                # Safely get items list
                items = data.get("items", [])
                if not items or not isinstance(items, list):
                    lang_text = f" for {language}" if language else ""
                    await interaction.followup.send(f"❌ No trending developers found{lang_text} for {range_label.lower()}.")
                    return

                # Extract unique developers from the repos
                developers_map = {}
                for repo in items:
                    if not isinstance(repo, dict):
                        continue
                    owner = repo.get("owner", {})
                    login = owner.get("login")
                    if login and login not in developers_map:
                        developers_map[login] = {
                            "login": login,
                            "avatar_url": owner.get("avatar_url"),
                            "html_url": owner.get("html_url"),
                            "repo_name": repo.get("name"),
                            "repo_url": repo.get("html_url"),
                            "repo_stars": repo.get("stargazers_count", 0),
                            "repo_description": repo.get("description", "No description")
                        }

                    if len(developers_map) >= 3:
                        break

                if not developers_map:
                    await interaction.followup.send(f"❌ No trending developers found for {range_label.lower()}.")
                    return

                # Create embeds for developers - one per developer to show profile pics
                lang_text = f" - {language.title()}" if language else " - All Languages"

                embeds = []
                for i, (login, dev) in enumerate(developers_map.items(), start=1):
                    repo_desc = dev.get("repo_description", "No description")
                    if repo_desc and len(repo_desc) > 100:
                        repo_desc = repo_desc[:100] + "..."

                    profile_url = dev.get('html_url', '#')
                    repo_name = dev.get('repo_name', 'N/A')
                    repo_url = dev.get('repo_url', '#')
                    repo_stars = format_number(dev.get('repo_stars', 0))

                    # Fetch detailed user information
                    user_data = await github_request(self.bot, f"https://api.github.com/users/{login}")

                    if user_data and isinstance(user_data, dict) and user_data not in ["rate_limited", "not_found"]:
                        followers = format_number(user_data.get('followers', 0))
                        following = format_number(user_data.get('following', 0))
                        public_repos = format_number(user_data.get('public_repos', 0))
                        avatar_url = user_data.get('avatar_url', '')
                    else:
                        # Fallback to basic data
                        followers = "N/A"
                        following = "N/A"
                        public_repos = "N/A"
                        avatar_url = dev.get('avatar_url', '')

                    # Create individual embed for each developer - all with titles for consistent width
                    if i == 1:
                        # First embed includes the main header
                        embed_title = f"🔥 Trending Developers{lang_text} - #{i}"
                        embed_desc = (
                            f"**Top {len(developers_map)} developers with popular repos from {range_label.lower()}**\n\n"
                            f"### [{login}]({profile_url})\n"
                            f"> 👥 **{followers}** Followers  •  **{following}** Following  •  📦 **{public_repos}** Repos\n"
                            f"> \n"
                            f"> 🔥 **Popular Repo:** [{repo_name}]({repo_url})  •  ⭐ **{repo_stars}** Stars\n"
                            f"> \n"
                            f"> _{repo_desc}_"
                        )
                    else:
                        # Subsequent embeds with consistent title format
                        embed_title = f"🔥 Trending Developers{lang_text} - #{i}"
                        embed_desc = (
                            f"### [{login}]({profile_url})\n"
                            f"> 👥 **{followers}** Followers  •  **{following}** Following  •  📦 **{public_repos}** Repos\n"
                            f"> \n"
                            f"> 🔥 **Popular Repo:** [{repo_name}]({repo_url})  •  ⭐ **{repo_stars}** Stars\n"
                            f"> \n"
                            f"> _{repo_desc}_"
                        )

                    embed = discord.Embed(
                        title=embed_title,
                        description=embed_desc,
                        color=0x2F3136,
                    )

                    # Set profile picture as thumbnail
                    if avatar_url:
                        embed.set_thumbnail(url=avatar_url)

                    # Only add footer to last embed
                    if i == len(developers_map):
                        embed.set_footer(text=f"Based on repos created in {range_label.lower()} | Powered by GitHub API")

                    embeds.append(embed)

                # Send all embeds
                await interaction.followup.send(embeds=embeds)

            else:
                await interaction.followup.send("❌ Invalid type selected. Choose 'repositories' or 'developers'.")
                return

        except Exception as e:
            logger.exception("github_trending command error")
            try:
                await interaction.followup.send("❌ An error occurred while fetching trending data.")
            except Exception:
                logger.debug("Failed to send error message to user")

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
