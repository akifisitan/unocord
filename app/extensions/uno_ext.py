from config import SERVER_IDS
from app.data.uno_players import (
    UnoLeaderboardPlayer,
    get_uno_players,
    add_uno_player,
    update_player,
)
from app.helpers.messages import delete_message, edit_message, send_message
from app.helpers.uno_logic import UnoGame, UnoPlayer, Card, Color
from app.utils.ui import PaginationView, ConfirmationView
from app.utils.colors import random_color
import nextcord
from nextcord import (
    slash_command,
    SlashOption,
    Interaction,
    Message,
    Embed,
    user_command,
)
from nextcord.ui import Button, View
from nextcord.ext.commands import Cog, Bot
import random as rnd
from io import StringIO

zw = "\u200b"
ongoing_games: dict[int, UnoGame] = {}
uno_players: dict[int, UnoLeaderboardPlayer] = get_uno_players()


class UnoStartGameView(View):
    def __init__(self, game_id: int, player_count: int, timeout: int):
        super().__init__(timeout=timeout)
        self.game_id = game_id
        self.player_count = player_count
        self.cancelled = False

    @nextcord.ui.button(label="Join / Leave", style=nextcord.ButtonStyle.blurple)
    async def btn_join_game(self, button: Button, interaction: Interaction):
        game = ongoing_games[self.game_id]
        if interaction.user.id in game.players:
            game.players.pop(interaction.user.id)
            await interaction.send(content="Left the game.", ephemeral=True)
        else:
            game.players[interaction.user.id] = UnoPlayer(
                interaction.user.id, interaction.user.name
            )
            await interaction.send(content="Joined the game.", ephemeral=True)
        embed = interaction.message.embeds[0]
        players_string = "\n".join(
            [f"<@{player.id}>" for player in game.players.values()]
        )
        embed.description = (
            f"Waiting for players to join. ({len(game.players)}/{self.player_count})\n"
            f"Players:\n{players_string}"
        )
        await interaction.followup.edit_message(
            message_id=interaction.message.id, embed=embed
        )
        if len(game.players) == self.player_count:
            self.stop()

    @nextcord.ui.button(label="Start", style=nextcord.ButtonStyle.green)
    async def btn_start_game(self, button: Button, interaction: Interaction):
        game = ongoing_games[self.game_id]
        if interaction.user.id != game.host_id:
            await interaction.send(
                content="Only the game host can start the game.", ephemeral=True
            )
            return
        if len(game.players) < 2:
            await interaction.send(
                content="There are not enough players to start the game.",
                ephemeral=True,
            )
            return
        self.stop()

    @nextcord.ui.button(label="Cancel", style=nextcord.ButtonStyle.red)
    async def btn_cancel_game(self, button: Button, interaction: Interaction):
        game = ongoing_games[self.game_id]
        if interaction.user.id != game.host_id:
            await interaction.send(
                content="Only the game host can cancel the game.", ephemeral=True
            )
            return
        await interaction.send(content="Game cancelled.", ephemeral=True)
        self.cancelled = True
        self.stop()


class CardButton(Button):
    def __init__(self, card: Card, enabled: bool):
        super().__init__(label=str(card.value.value), emoji=card.color.value)
        self.card = card
        self.disabled = not enabled

    async def callback(self, interaction: Interaction) -> None:
        self.view.chosen_card = self.card
        self.view.stop()


class ChooseCardView(View):
    def __init__(self, pile_top_card: Card, hand: list[Card]):
        super().__init__(timeout=7)
        self.chosen_card = None
        self.timed_out = False
        for card in hand:
            if UnoGame.card_is_eligible(card, pile_top_card):
                self.add_item(CardButton(card, enabled=True))
            else:
                self.add_item(CardButton(card, enabled=False))

    async def on_timeout(self) -> None:
        self.timed_out = True
        self.stop()


class ShowHandView(View):
    def __init__(self, hand: list[Card]):
        super().__init__(timeout=None)
        for card in hand:
            self.add_item(CardButton(card, enabled=False))


class PickColorButton(Button):
    def __init__(self, color: Color):
        super().__init__(label=zw, emoji=color.value)
        self.color = color

    async def callback(self, interaction: Interaction) -> None:
        self.view.chosen_color = self.color
        self.view.stop()


class PickColorView(View):
    def __init__(self):
        super().__init__(timeout=7)
        self.chosen_color = None
        self.timed_out = False
        for color in (Color.RED, Color.GREEN, Color.BLUE, Color.YELLOW):
            self.add_item(PickColorButton(color))

    async def on_timeout(self) -> None:
        self.timed_out = True
        self.stop()


class PickPlayerButton(Button):
    def __init__(self, player_id: int, player_name: str):
        super().__init__(label=player_name)
        self.player_id = player_id

    async def callback(self, interaction: Interaction) -> None:
        self.view.chosen_player_id = self.player_id
        self.view.chosen_player_username = self.label
        self.view.stop()


class PickPlayerView(View):
    def __init__(self, game_players: dict, current_player_id: int):
        super().__init__(timeout=7)
        self.chosen_player_id = -1
        self.chosen_player_username = None
        self.timed_out = False
        for player_id in game_players:
            if player_id != current_player_id:
                self.add_item(
                    PickPlayerButton(player_id, game_players[player_id].username)
                )

    async def on_timeout(self) -> None:
        self.timed_out = True
        self.stop()


class UnoOngoingGameView(View):
    def __init__(self, game_id: int, timeout: int):
        super().__init__(timeout=timeout)
        self.game_id = game_id
        self.made_move = None
        self.drawn_card_playable = False
        self.skipped_player_id = None
        self.swapped_player_id = None
        self.play_in_progress = False
        self.card_choice_in_progress = False
        self.color_choice_in_progress = False
        self.swap_player_choice_in_progress = False
        self.end_game = None
        self.current_player_left_game = False

    async def pick_player_from_view(
        self, interaction: Interaction, pick_player_view: PickPlayerView
    ) -> int | None:
        self.swap_player_choice_in_progress = True
        await pick_player_view.wait()
        if pick_player_view.timed_out:
            self.swap_player_choice_in_progress = False
            return None
        chosen_player_id = pick_player_view.chosen_player_id
        chosen_player_username = pick_player_view.chosen_player_username
        await interaction.edit_original_message(
            content=f"Picked {chosen_player_username}.", view=None
        )
        self.swap_player_choice_in_progress = False
        return chosen_player_id

    async def pick_color_from_view(
        self, interaction: Interaction, pick_color_view: PickColorView
    ) -> Color | None:
        self.color_choice_in_progress = True
        await pick_color_view.wait()
        if pick_color_view.timed_out:
            self.color_choice_in_progress = False
            return None
        chosen_color = pick_color_view.chosen_color
        await interaction.edit_original_message(
            content=f"Picked {chosen_color.value}", view=None
        )
        self.color_choice_in_progress = False
        return chosen_color

    async def choose_card_from_view(
        self, interaction: Interaction, choose_card_view: ChooseCardView
    ) -> Card | None:
        self.card_choice_in_progress = True
        await choose_card_view.wait()
        if choose_card_view.timed_out:
            self.card_choice_in_progress = False
            return None
        if choose_card_view.chosen_card.is_swap_hands():
            pick_player_view = PickPlayerView(
                ongoing_games[self.game_id].players, interaction.user.id
            )
            await interaction.edit_original_message(
                content="Pick a player to swap hands with.", view=pick_player_view
            )
            chosen_player_id = await self.pick_player_from_view(
                interaction, pick_player_view
            )
            if not chosen_player_id:
                self.card_choice_in_progress = False
                return None
            self.swapped_player_id = chosen_player_id
        if choose_card_view.chosen_card.is_wildcard():
            pick_color_view = PickColorView()
            await interaction.edit_original_message(
                content="Pick a new color.", view=pick_color_view
            )
            chosen_color = await self.pick_color_from_view(interaction, pick_color_view)
            if not chosen_color:
                self.card_choice_in_progress = False
                return None
            choose_card_view.chosen_card.color = chosen_color
        self.card_choice_in_progress = False
        return choose_card_view.chosen_card

    async def draw_card_and_play(
        self, interaction: Interaction, game: UnoGame, player: UnoPlayer
    ):
        card = game.draw_card(player)
        # In the super low chance case the player has 25 cards and somehow has no playable card
        if not card:
            await interaction.edit_original_message(
                content="You have the maximum amount of cards.", view=None
            )
            self.made_move = "MAX_CARDS", None
            self.stop()
            return
        if not UnoGame.card_is_eligible(card, game.get_top_card()):
            await interaction.edit_original_message(
                content=f"You drew {card}. Skipping your turn.", view=None
            )
            await interaction.delete_original_message()
            self.made_move = "DRAW_CARD", card
            self.stop()
            return
        self.drawn_card_playable = True
        played_card = card
        if played_card.is_swap_hands():
            pick_player_view = PickPlayerView(game.players, player.id)
            await interaction.edit_original_message(
                content="Pick a player to swap hands with.", view=pick_player_view
            )
            chosen_player_id = await self.pick_player_from_view(
                interaction, pick_player_view
            )
            if not chosen_player_id:
                self.play_in_progress = False
                await interaction.edit_original_message(
                    content="You took too long. Press play again.", view=None
                )
                return
            game.play_card(player, played_card, chosen_player_id)
            self.swapped_player_id = chosen_player_id
        if played_card.is_wildcard():
            pick_color_view = PickColorView()
            await interaction.edit_original_message(
                content="Pick a new color.", view=pick_color_view
            )
            chosen_color = await self.pick_color_from_view(interaction, pick_color_view)
            if not chosen_color:
                self.play_in_progress = False
                await interaction.edit_original_message(
                    content="You took too long. Press play again.", view=None
                )
                return
            played_card.color = chosen_color
        if not self.swapped_player_id:
            self.skipped_player_id = game.play_card(player, played_card)
        await interaction.edit_original_message(
            content=f"You drew and played {played_card}", view=None
        )
        await interaction.delete_original_message()
        self.made_move = "PLAY_CARD", played_card
        self.stop()

    @nextcord.ui.button(
        label=f"{zw} Play Card {zw} {zw}", style=nextcord.ButtonStyle.green, row=0
    )
    async def btn_play_card(self, button: Button, interaction: Interaction):
        game = ongoing_games[self.game_id]
        if interaction.user.id not in game.players:
            await interaction.send(content="You are not in the game.", ephemeral=True)
            return
        if interaction.user.id != game.current_player_id:
            await interaction.send(content="Please wait for your turn.", ephemeral=True)
            return
        if self.color_choice_in_progress:
            await interaction.send(
                content="Color pick is in progress. Pick a color or press play again in 5 seconds.",
                ephemeral=True,
            )
            return
        if self.swap_player_choice_in_progress:
            await interaction.send(
                content="Player swap in progress. Pick a player or press play again in 5 seconds.",
                ephemeral=True,
            )
            return
        if self.card_choice_in_progress:
            await interaction.send(
                content="Card pick in progress. Pick a card or press play again in 5 seconds.",
                ephemeral=True,
            )
            return
        if self.play_in_progress:
            await interaction.send(
                content="Play in progress. Press play again in 5 seconds.",
                ephemeral=True,
            )
            return
        self.play_in_progress = True
        player = game.players[interaction.user.id]
        if not game.has_eligible_card(player):
            await interaction.send(
                content="You do not have any eligible cards. Drawing a card...",
                ephemeral=True,
            )
            await self.draw_card_and_play(interaction, game, player)
            return
        choose_card_view = ChooseCardView(
            pile_top_card=game.get_top_card(), hand=player.hand
        )
        await interaction.send(
            content="Select a card to play.", view=choose_card_view, ephemeral=True
        )
        chosen_card = await self.choose_card_from_view(interaction, choose_card_view)
        if not chosen_card:
            await interaction.edit_original_message(
                content="You took too long. Press play again.", view=None
            )
            self.play_in_progress = False
            return
        if self.swapped_player_id:
            game.play_card(player, chosen_card, self.swapped_player_id)
        else:
            self.skipped_player_id = game.play_card(player, chosen_card)
        await interaction.edit_original_message(
            content=f"You played {chosen_card}", view=None
        )
        await interaction.delete_original_message()
        self.made_move = "PLAY_CARD", chosen_card
        self.stop()

    @nextcord.ui.button(label="Show Hand", style=nextcord.ButtonStyle.blurple, row=1)
    async def btn_show_hand(self, button: Button, interaction: Interaction):
        game = ongoing_games[self.game_id]
        if interaction.user.id not in game.players:
            await interaction.send(content="You are not in the game.", ephemeral=True)
            return
        view = ShowHandView(hand=game.players[interaction.user.id].hand)
        await interaction.send(content="Your hand:", view=view, ephemeral=True)

    @nextcord.ui.button(label=f"{zw} {zw} {zw} Say Uno {zw} {zw} {zw} {zw}", row=1)
    async def btn_say_uno(self, button: Button, interaction: Interaction):
        game = ongoing_games[self.game_id]
        if interaction.user.id not in game.players:
            await interaction.send(content="You are not in the game.", ephemeral=True)
            return
        player = game.players[interaction.user.id]
        if interaction.user.id == game.current_player_id and len(game.players) > 2:
            await interaction.send(
                content="You cannot say uno on your turn.", ephemeral=True
            )
            return
        if not player.one_card_left():
            await interaction.send(
                content="You are not eligible to say uno.", ephemeral=True
            )
            return
        if player.said_uno:
            await interaction.send(content="You have already said uno.", ephemeral=True)
            return
        player.said_uno = True
        await interaction.channel.send(
            content=f"<@{interaction.user.id}> said uno.", delete_after=15
        )

    @nextcord.ui.button(label="Draw & Skip", row=0)
    async def btn_draw_card(self, button: Button, interaction: Interaction):
        game = ongoing_games[self.game_id]
        if interaction.user.id not in game.players:
            await interaction.send(content="You are not in the game.", ephemeral=True)
            return
        if interaction.user.id != game.current_player_id:
            await interaction.send(content="Please wait for your turn.", ephemeral=True)
            return
        if self.play_in_progress:
            await interaction.send(
                content="Play in progress. Press play again in 5 seconds.",
                ephemeral=True,
            )
            return
        player = game.players[interaction.user.id]
        card = game.draw_card(player)
        if not card:
            if game.has_eligible_card(player):
                await interaction.send(
                    content="You have the maximum amount of cards. Play one.",
                    ephemeral=True,
                )
                return
            await interaction.send(
                content="You have the maximum amount of cards and no playable cards, "
                "skipping your turn",
                ephemeral=True,
            )
            self.made_move = "MAX_CARDS", None
        else:
            await interaction.send(
                content=f"You drew {card}. Skipping your turn.", ephemeral=True
            )
            self.made_move = "DRAW_CARD", card
        self.stop()

    @nextcord.ui.button(label="Leave", style=nextcord.ButtonStyle.red, row=0)
    async def btn_leave_game(self, button: Button, interaction: Interaction):
        game = ongoing_games[self.game_id]
        if interaction.user.id not in game.players:
            await interaction.send(content="You are not in the game.", ephemeral=True)
            return
        confirm_view = ConfirmationView(timeout=10)
        if len(game.players) <= 2:
            await interaction.send(
                content="The game will end if you leave it, are you sure you want to leave it?",
                view=confirm_view,
                ephemeral=True,
            )
        else:
            await interaction.send(
                content="Are you sure you want to leave the game?",
                view=confirm_view,
                ephemeral=True,
            )
        confirm = await confirm_view.wait()
        if not confirm and confirm_view.value:
            if len(game.players) <= 2:
                self.end_game = "few_players"
                self.stop()
                await interaction.delete_original_message()
                return
            if interaction.user.id == game.current_player_id:
                self.current_player_left_game = True
                self.stop()
            else:
                game.remove_player(interaction.user.id)
                await interaction.channel.send(
                    content=f"{interaction.user.mention} left the game."
                )
        await interaction.delete_original_message()

    @nextcord.ui.button(
        label=f"{zw} {zw} End {zw} {zw}", style=nextcord.ButtonStyle.red, row=1
    )
    async def btn_end_game(self, button: Button, interaction: Interaction):
        game = ongoing_games[self.game_id]
        if interaction.user.id != game.host_id:
            await interaction.send(
                content="Only the host can end the game.", ephemeral=True
            )
            return
        confirm_view = ConfirmationView(timeout=10)
        await interaction.send(
            content="Are you sure you want to end the game?",
            view=confirm_view,
            ephemeral=True,
        )
        confirm = await confirm_view.wait()
        if not confirm and confirm_view.value:
            self.end_game = "host"
            self.stop()
        await interaction.delete_original_message()


def calculate_game_stats(game: UnoGame):
    total_drawn_cards, total_turns_skipped, total_played_cards = 0, 0, 0
    for player in game.players.values():
        total_played_cards += player.played_cards
        total_turns_skipped += player.turns_skipped
        total_drawn_cards += player.drawn_cards
    return total_drawn_cards, total_turns_skipped, total_played_cards


def update_player_stats(player_dict: dict[int, UnoPlayer], winner_id: int):
    for player_id, player in player_dict.items():
        new_player = False
        if player_id not in uno_players:
            lb_player = UnoLeaderboardPlayer(player_id, player.username)
            new_player = True
        else:
            lb_player = uno_players[player_id]
        if lb_player.user_id == winner_id:
            lb_player.wins += 1
        lb_player.played += 1
        lb_player.drawn_cards += player.drawn_cards
        lb_player.turns_skipped += player.turns_skipped
        lb_player.played_cards += player.played_cards
        if new_player:
            uno_players[lb_player.user_id] = lb_player
            add_uno_player(lb_player)
        else:
            update_player(player_id, uno_players[player_id])


class Uno(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.phrases = ["dunked on", "trolled", "owned", "rekt"]

    @slash_command(name="uno", guild_ids=SERVER_IDS)
    async def uno(self, interaction):
        pass

    @uno.subcommand(name="play", description="Play a game of uno")
    async def uno_play(
        self,
        interaction,
        players: int = SlashOption(
            description="Number of players in the game", min_value=2, max_value=10
        ),
        cards: int = SlashOption(
            description="Number of cards each player starts with",
            min_value=3,
            max_value=10,
            default=7,
        ),
    ):
        await interaction.response.defer(ephemeral=True)
        if interaction.channel.id in ongoing_games:
            await interaction.send(
                content="There's already a game being hosted in this channel."
            )
            return
        game = UnoGame(
            interaction.channel.id, interaction.user.id, initial_card_count=cards
        )
        ongoing_games[game.id] = game
        game.players[interaction.user.id] = UnoPlayer(
            interaction.user.id, interaction.user.name
        )
        embed = Embed(
            title="Uno Game",
            color=random_color(),
            timestamp=nextcord.utils.utcnow(),
            description=f"Waiting for players to join. (1/{players})\nPlayers:\n"
            f"<@{interaction.user.id}>",
        )
        embed.add_field(name="Cards per player", value=cards)
        embed.add_field(
            name="Info",
            value=f"The game will begin when all {players} players have joined or "
            f"when the host starts the game.",
            inline=False,
        )
        embed.set_author(
            name=self.bot.user.name,
            icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None,
        )
        embed.set_footer(
            text=f"Hosted by {interaction.user.name}",
            icon_url=interaction.user.avatar.url,
        )
        if self.bot.user.avatar:
            embed.set_thumbnail(self.bot.user.avatar.url)
        start_game_view = UnoStartGameView(game.id, player_count=players, timeout=600)
        uno_role = nextcord.utils.get(interaction.guild.roles, name="Uno")
        ping = uno_role.mention if uno_role else None
        start_game_msg: Message = await interaction.channel.send(
            content=ping, embed=embed, view=start_game_view
        )
        await interaction.send("Waiting for players to join.")
        if await start_game_view.wait() or start_game_view.cancelled:
            await edit_message(
                start_game_msg,
                "The game timed out or was cancelled.",
                embed=None,
                view=None,
            )
            if game.id in ongoing_games:
                ongoing_games.pop(game.id)
            await delete_message(start_game_msg, 5)
            return
        timeout = 60
        game.start_game()
        ongoing_game_view = UnoOngoingGameView(game.id, timeout=timeout)
        turn_number = 1
        embed.title = f"Turn {turn_number}"
        embed.description = "The game has begun"
        current_member = interaction.guild.get_member(game.current_player_id)
        embed.set_author(name=current_member.name, icon_url=current_member.avatar.url)
        turn_order = [
            f"{index}. <@{player_id}> **({len(game.players[player_id].hand)})**"
            for index, player_id in enumerate(game.play_order)
        ]
        embed.clear_fields()
        embed.add_field(name="Turn Order", value="\n".join(turn_order), inline=False)
        embed.add_field(
            name="Current Turn", value=f"<@{game.current_player_id}>", inline=True
        )
        embed.add_field(name="Current Card", value=game.get_top_card(), inline=True)
        embed.add_field(
            name="Next Turn", value=f"<@{game.next_player_id}>", inline=True
        )
        await delete_message(start_game_msg)
        game_msg = await interaction.channel.send(
            content=f"Game started, <@{game.current_player_id}>'s turn.",
            embed=embed,
            view=ongoing_game_view,
        )
        # Wait until the player that has the current move makes a move or the view times out
        consecutive_skips = 0
        while True:
            timed_out = await ongoing_game_view.wait()
            if ongoing_game_view.end_game:
                if game.id in ongoing_games:
                    ongoing_games.pop(game.id)
                await delete_message(game_msg)
                if ongoing_game_view.end_game == "host":
                    await send_message(
                        interaction.channel,
                        "The game was ended by the host.",
                        delete_after=10,
                    )
                else:
                    await send_message(
                        interaction.channel,
                        "The game was ended as there were not enough players remaining.",
                        delete_after=10,
                    )
                return
            winner = game.check_winner()
            if winner:
                if game.id in ongoing_games:
                    ongoing_games.pop(game.id)
                embed.description = "Game has ended"
                embed.clear_fields().add_field(
                    name="Winner", value=f"<@{winner}>", inline=False
                )
                game_stats = calculate_game_stats(game)
                embed.add_field(name="Played Cards", value=game_stats[2])
                embed.add_field(name="Cards Drawn", value=game_stats[0])
                embed.add_field(name="Turns Skipped", value=game_stats[1])
                await delete_message(game_msg)
                await interaction.channel.send(embed=embed)
                update_player_stats(game.players, winner)
                return
            player_left_game, leaving_player_id = (
                ongoing_game_view.current_player_left_game,
                game.current_player_id,
            )
            if player_left_game:
                round_result = f"<@{game.current_player_id}> left the game."
            elif timed_out:
                random_draw = rnd.randint(2, 4)
                game.draw_cards(game.players[game.current_player_id], random_draw)
                round_result = f"<@{game.current_player_id}> randomly drew {random_draw} for taking too long to move"
                consecutive_skips += 1
                if consecutive_skips > len(game.players) + 1:
                    if game.id in ongoing_games:
                        ongoing_games.pop(game.id)
                    await edit_message(
                        game_msg,
                        content="Game is inactive, ending the game.",
                        embed=None,
                        view=None,
                    )
                    await delete_message(game_msg, delay=5)
                    return
                await interaction.channel.send(
                    f"<@{game.current_player_id}> randomly drew {random_draw} for "
                    f"taking too long to move",
                    delete_after=5,
                )
            else:
                consecutive_skips = 0
                made_move, played_card = ongoing_game_view.made_move
                if ongoing_game_view.drawn_card_playable:
                    if played_card.is_punishing():
                        round_result = (
                            f"<@{game.current_player_id}> drew and {rnd.choice(self.phrases)} "
                            f"<@{ongoing_game_view.skipped_player_id}> with {played_card}"
                        )
                    elif (
                        played_card.is_swap_hands()
                        and ongoing_game_view.swapped_player_id
                    ):
                        round_result = (
                            f"<@{game.current_player_id}> drew and swapped hands with "
                            f"<@{ongoing_game_view.swapped_player_id}> with {played_card}"
                        )
                    else:
                        round_result = (
                            f"<@{game.current_player_id}> drew and played {played_card}"
                        )
                else:
                    if made_move == "DRAW_CARD":
                        round_result = f"<@{game.current_player_id}> drew a card"
                    elif made_move == "MAX_CARDS":
                        round_result = (
                            f"<@{game.current_player_id}> reached the card limit"
                        )
                    elif played_card.is_punishing():
                        round_result = (
                            f"<@{game.current_player_id}> {rnd.choice(self.phrases)} "
                            f"<@{ongoing_game_view.skipped_player_id}> with {played_card}"
                        )
                    elif (
                        played_card.is_swap_hands()
                        and ongoing_game_view.swapped_player_id
                    ):
                        round_result = (
                            f"<@{game.current_player_id}> swapped hands with "
                            f"<@{ongoing_game_view.swapped_player_id}> with {played_card}"
                        )
                    else:
                        round_result = (
                            f"<@{game.current_player_id}> played {played_card}"
                        )
            if (
                player_left_game
                and game.player_id_that_has_to_say_uno == leaving_player_id
            ):
                game.player_id_that_has_to_say_uno = -1
            if game.player_id_that_has_to_say_uno != -1:
                player_that_has_to_say_uno = game.players[
                    game.player_id_that_has_to_say_uno
                ]
                if not player_that_has_to_say_uno.said_uno and len(game.players) > 2:
                    round_result = f"<@{player_that_has_to_say_uno.id}> forgot to say uno.\n{round_result}"
                    game.draw_cards(player_that_has_to_say_uno, 2)
                player_that_has_to_say_uno.said_uno = False
                game.player_id_that_has_to_say_uno = -1
            if game.check_for_uno(game.current_player_id):
                game.player_id_that_has_to_say_uno = game.current_player_id
            turn_number += 1
            embed.title = f"Turn {turn_number}"
            embed.description = round_result
            game.advance_turn()
            if player_left_game:
                game.remove_player(leaving_player_id)
            ongoing_game_view = UnoOngoingGameView(game.id, timeout=timeout)
            current_member = interaction.guild.get_member(game.current_player_id)
            embed.set_author(
                name=current_member.name, icon_url=current_member.avatar.url
            )
            embed.clear_fields()
            turn_order = [
                f"{index}. <@{player_id}> **({len(game.players[player_id].hand)})**"
                for index, player_id in enumerate(game.play_order)
            ]
            embed.add_field(
                name="Turn Order", value="\n".join(turn_order), inline=False
            )
            embed.add_field(
                name="Current Turn", value=f"<@{game.current_player_id}>", inline=True
            )
            embed.add_field(name="Current Card", value=game.get_top_card(), inline=True)
            embed.add_field(
                name="Next Turn", value=f"<@{game.next_player_id}>", inline=True
            )
            await delete_message(game_msg)
            game_msg = await interaction.channel.send(
                content=f"<@{game.current_player_id}>'s turn.",
                embed=embed,
                view=ongoing_game_view,
            )

    @uno.subcommand(name="leaderboard", description="View the leaderboard for Uno")
    async def uno_leaderboard(
        self,
        interaction: Interaction,
        name: str = SlashOption(
            description="The name of the leaderboard to view",
            choices={"Wins": "wins", "Win Rate": "winrate"},
        ),
        page_length: int = SlashOption(
            description="The number of players to show per page",
            default=5,
            min_value=3,
            max_value=10,
        ),
        hidden: bool = SlashOption(
            description="Whether to hide the leaderboard from other players",
            default=True,
        ),
    ):
        await interaction.response.defer(ephemeral=hidden)
        embed = Embed(color=random_color())
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        if name == "winrate":
            embed.title = "Uno Win Rate Leaderboard"
            embed.set_footer(
                text="Players with less than 20 games played are ranked separately"
            )
            eligible_players, ineligible_players = [], []
            for uno_player in uno_players.values():
                if uno_player.played >= 20:
                    eligible_players.append(uno_player)
                elif uno_player.played > 0 and uno_player.wins > 0:
                    ineligible_players.append(uno_player)
            eligible_players.sort(
                key=lambda p: (p.wins / p.played, p.played, p.wins), reverse=True
            )
            ineligible_players.sort(
                key=lambda p: (p.wins / p.played, p.played, p.wins), reverse=True
            )
            players_sorted = eligible_players + ineligible_players
        else:
            embed.title = "Uno Wins Leaderboard"
            eligible_players = [
                uno_player for uno_player in uno_players.values() if uno_player.wins > 0
            ]
            players_sorted = sorted(
                eligible_players, key=lambda p: (p.wins, p.played), reverse=True
            )
        leaderboard = StringIO()
        embed_pages = []
        for ranking, player in enumerate(players_sorted):
            stats = (
                f"Wins: ``{player.wins} ({player.played})``\n"
                f"Win Rate: ``{round(player.wins / player.played * 100, 2)}%``\n"
            )
            leaderboard.write(f"#**{ranking + 1}** <@{player.user_id}>\n{stats}\n")
            if (ranking + 1) % page_length == 0:
                embed_pages.append(leaderboard.getvalue())
                leaderboard = StringIO()
        if len(players_sorted) < page_length:
            embed.description = leaderboard.getvalue()
            await interaction.send(embed=embed)
            return
        # Add the remaining page that got left out
        if len(players_sorted) % page_length != 0:
            remaining_players = len(players_sorted) % page_length
            remaining_player_string = ""
            for ranking, player in enumerate(
                players_sorted[-remaining_players:],
                len(players_sorted) - remaining_players,
            ):
                stats = (
                    f"Wins: ``{player.wins} ({player.played})``\n"
                    f"Win Rate: ``{round(player.wins / player.played * 100, 2)}%``\n"
                )
                remaining_player_string += (
                    f"#**{ranking + 1}** <@{player.user_id}>\n{stats}\n"
                )
            embed_pages.append(remaining_player_string)
        embed.description = embed_pages[0]
        pagination_view = PaginationView(embed=embed, pages=embed_pages, timeout=20)
        await interaction.send(embed=embed, view=pagination_view)
        if await pagination_view.wait():
            embed.description = embed_pages[0]
            await interaction.edit_original_message(embed=embed, view=None)

    @uno.subcommand(name="stats", description="Check a user's Uno stats")
    async def uno_stats(
        self,
        interaction: Interaction,
        user: nextcord.Member = SlashOption(
            description="User to check stats of", default=None
        ),
        hidden: bool = SlashOption(
            description="Whether to hide the stats from other players", default=True
        ),
    ):
        await interaction.response.defer(ephemeral=hidden)
        user = user if user else interaction.user
        if user.id not in uno_players:
            await interaction.send(
                f"{user.mention} hasn't played Uno yet.", ephemeral=True
            )
            return
        player = uno_players[user.id]
        stats = (
            f"```"
            f"Wins: {player.wins}\n"
            f"Played: {player.played}\n"
            f"Win Rate: {round(player.wins / player.played * 100, 2)}%\n"
            f"Cards Played: {player.played_cards}\n"
            f"Cards Drawn: {player.drawn_cards}\n"
            f"Times Skipped: {player.turns_skipped}"
            f"```"
        )
        embed = Embed(description=stats, color=random_color())
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_author(name=user.name, icon_url=user.avatar.url)
        await interaction.send(embed=embed)

    @user_command(name="Uno Stats", guild_ids=SERVER_IDS)
    async def user_uno_stats(self, interaction: Interaction, user: nextcord.Member):
        await interaction.response.defer(ephemeral=True)
        if user.id not in uno_players:
            await interaction.send(f"{user.mention} hasn't played Uno yet.")
            return
        player = uno_players[user.id]
        stats = (
            f"```"
            f"Wins: {player.wins}\n"
            f"Played: {player.played}\n"
            f"Win Rate: {round(player.wins / player.played * 100, 2)}%\n"
            f"Cards Played: {player.played_cards}\n"
            f"Cards Drawn: {player.drawn_cards}\n"
            f"Times Skipped: {player.turns_skipped}"
            f"```"
        )
        embed = Embed(description=stats, color=random_color())
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_author(name=user.name, icon_url=user.avatar.url)
        await interaction.send(embed=embed)


def setup(bot):
    bot.add_cog(Uno(bot))
