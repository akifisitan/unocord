from config import firebase_database
from dataclasses import dataclass


@dataclass
class UnoLeaderboardPlayer:
    user_id: int
    username: str
    wins: int = 0
    played: int = 0
    drawn_cards: int = 0
    turns_skipped: int = 0
    played_cards: int = 0


uno_database = firebase_database.child("uno")
uno_leaderboard = uno_database.child("leaderboard")


def get_uno_players() -> dict[int, UnoLeaderboardPlayer]:
    result = uno_leaderboard.get()
    if not result:
        return {}
    return {
        int(key): UnoLeaderboardPlayer(
            user_id=int(key),
            username=value.get("username"),
            wins=value.get("wins", 0),
            played=value.get("played", 0),
            drawn_cards=value.get("drawn_cards", 0),
            turns_skipped=value.get("turns_skipped", 0),
            played_cards=value.get("played_cards", 0),
        )
        for key, value in result.items()
    }


def add_uno_player(player: UnoLeaderboardPlayer):
    try:
        uno_leaderboard.update(
            {
                str(player.user_id): {
                    "username": player.username,
                    "wins": player.wins,
                    "played": player.played,
                    "drawn_cards": player.drawn_cards,
                    "turns_skipped": player.turns_skipped,
                    "played_cards": player.played_cards,
                }
            }
        )
    except Exception as e:
        print(e)


def update_player(user_id: int, player: UnoLeaderboardPlayer):
    try:
        player_ref = uno_leaderboard.child(str(user_id))
        player_ref.update(
            {
                "username": player.username,
                "wins": player.wins,
                "played": player.played,
                "drawn_cards": player.drawn_cards,
                "turns_skipped": player.turns_skipped,
                "played_cards": player.played_cards,
            }
        )
    except Exception as e:
        print(e)
