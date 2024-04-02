from dataclasses import dataclass
from collections import deque
from enum import Enum
import random


class Value(Enum):
    ZERO = "0"
    ONE = "1"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    DRAW_TWO = "+2"
    BLOCK = "🚫"
    REVERSE = "🔁"
    DRAW_FOUR = "+4🌈"
    RAINBOW = "🌈"
    SWAP_HANDS = "🤝"


class Color(Enum):
    RED = "🟥"
    BLUE = "🟦"
    GREEN = "🟩"
    YELLOW = "🟨"
    BLACK = "⬛"
    WHITE = "⬜"


@dataclass(eq=True, order=True)
class Card:
    value: Value
    color: Color

    def __repr__(self):
        return f"{self.color.value} {self.value.value}"

    def is_special(self):
        return self.value in {
            Value.DRAW_TWO,
            Value.BLOCK,
            Value.REVERSE,
            Value.DRAW_FOUR,
            Value.RAINBOW,
            Value.SWAP_HANDS,
        }

    def is_swap_hands(self):
        return self.value == Value.SWAP_HANDS

    def is_wildcard(self):
        return self.value in {Value.DRAW_FOUR, Value.RAINBOW}

    def is_punishing(self):
        return self.value in {Value.BLOCK, Value.DRAW_FOUR, Value.DRAW_TWO}


class UnoPlayer:
    def __init__(self, player_id: int, username: str):
        self.id = player_id
        self.username = username
        self.hand: list[Card] = []
        self.drawn_cards = 0
        self.turns_skipped = 0
        self.played_cards = 0
        self.said_uno = False

    def __repr__(self):
        return f"UnoPlayer(Id: {self.id}, Hand: {self.hand})"

    def remove_from_hand(self, card: Card) -> None:
        try:
            self.hand.remove(card)
            self.played_cards += 1
        except ValueError:
            print(f"Card {card} not in {self.username}'s hand. Hand: {self.hand}")

    def add_to_hand(self, card: Card) -> Card:
        self.hand.append(card)
        self.drawn_cards += 1
        return card

    def one_card_left(self):
        return len(self.hand) == 1


class UnoGame:
    def __init__(self, game_id: int, host_id: int, initial_card_count: int = 7):
        self.id = game_id
        self.host_id = host_id
        self.initial_card_count = initial_card_count
        self.current_player_id = None
        self.next_player_id = None
        self.play_order: deque[int] = deque()
        self.deck: list[Card] = []
        self.discard_pile: list[Card] = []
        self.players: dict[int, UnoPlayer] = {}
        self.player_id_that_has_to_say_uno = -1

    @staticmethod
    def generate_deck():
        eligible_values = [
            value
            for value in Value
            if value not in {Value.DRAW_FOUR, Value.RAINBOW, Value.SWAP_HANDS}
        ]
        new_deck = []
        for color in Color:
            if color not in {Color.BLACK, Color.WHITE}:
                for value in eligible_values:
                    for _ in range(2):
                        new_deck.append(Card(value, color))
        for _ in range(4):
            new_deck.append(Card(Value.DRAW_FOUR, Color.BLACK))
            new_deck.append(Card(Value.RAINBOW, Color.BLACK))
        if random.randint(1, 100) == 50:
            new_deck.append(Card(Value.SWAP_HANDS, Color.WHITE))
        random.shuffle(new_deck)
        return new_deck

    def start_game(self):
        self.deck = self.generate_deck()
        for _ in range(self.initial_card_count):
            for player in self.players.values():
                player.add_to_hand(self.deck.pop())
        initial_card = self.deck.pop()
        while initial_card.is_special():
            initial_card = self.deck.pop()
        self.discard_pile.append(initial_card)
        self.play_order = deque(self.players.keys())
        random.shuffle(self.play_order)
        self.current_player_id = self.play_order[0]
        self.next_player_id = self.play_order[1]

    @staticmethod
    def card_is_eligible(card: Card, top_pile: Card) -> bool:
        return (
            card.color in {Color.BLACK, Color.WHITE}
            or top_pile.color in {Color.BLACK, Color.WHITE}
            or card.color == top_pile.color
            or card.value == top_pile.value
        )

    def has_eligible_card(self, player: UnoPlayer):
        if len(player.hand) > 1:
            return any(
                card
                for card in player.hand
                if self.card_is_eligible(card, self.discard_pile[-1])
            )
        return (
            self.card_is_eligible(player.hand[-1], self.discard_pile[-1])
            and not player.hand[-1].is_wildcard()
        )

    def play_card(
        self, player: UnoPlayer, card: Card, swapped_player_id: int = None
    ) -> int | None:
        player.remove_from_hand(card)
        self.discard_pile.append(card)
        skipped_player_id = None
        if swapped_player_id and card.value == Value.SWAP_HANDS:
            self.swap_hands(player.id, swapped_player_id)
        elif card.value == Value.DRAW_TWO:
            skipped_player_id = self.skip_next_player()
            self.draw_cards(self.players[skipped_player_id], 2)
        elif card.value == Value.DRAW_FOUR:
            skipped_player_id = self.skip_next_player()
            self.draw_cards(self.players[skipped_player_id], 4)
        elif card.value == Value.BLOCK:
            skipped_player_id = self.skip_next_player()
        elif card.value == Value.REVERSE:
            if len(self.play_order) == 2:
                skipped_player_id = self.skip_next_player()
            else:
                self.reverse_play_order()
        return skipped_player_id

    def advance_turn(self):
        self.play_order.rotate(-1)
        self.current_player_id = self.play_order[0]
        self.next_player_id = self.play_order[1]
        if len(self.deck) < 5:
            self.deck.extend(self.generate_deck())

    def skip_next_player(self):
        self.play_order.rotate(-1)
        skipped_player_id = self.play_order[0]
        self.players[skipped_player_id].turns_skipped += 1
        return skipped_player_id

    def reverse_play_order(self):
        self.play_order.reverse()
        self.play_order.rotate(1)

    def draw_card(self, player: UnoPlayer) -> Card | None:
        if len(player.hand) >= 25:
            return None
        card = self.deck.pop()
        player.add_to_hand(card)
        return card

    def get_top_card(self):
        return self.discard_pile[-1]

    def draw_cards(self, player: UnoPlayer, amount: int) -> list[Card]:
        if len(player.hand) >= 25:
            return []
        if len(player.hand) + amount > 25:
            amount = 25 - len(player.hand)
        drawn_cards = []
        for _ in range(amount):
            card = self.deck.pop()
            player.add_to_hand(card)
            drawn_cards.append(card)
        return drawn_cards

    def check_winner(self):
        for player in self.players.values():
            if len(player.hand) == 0:
                return player.id
        return None

    def check_for_uno(self, player_id: int):
        return self.players[player_id].one_card_left()

    def remove_player(self, player_id: int):
        if player_id == self.player_id_that_has_to_say_uno:
            self.player_id_that_has_to_say_uno = -1
        self.players.pop(player_id)
        self.play_order.remove(player_id)

    def swap_hands(self, p1_id: int, p2_id: int):
        self.players[p1_id].hand, self.players[p2_id].hand = (
            self.players[p2_id].hand,
            self.players[p1_id].hand,
        )
