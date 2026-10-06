"""A ranked-ladder rating kernel built on the standard library only.

Every call carries the day it happened on, so nothing in this module reads a
clock, a file, a network or a random source: a ladder replayed with the same
calls always lands on the same numbers.  Ratings are floats and callers are
expected to compare them with a tolerance.

A ladder keeps one record per player: the rating, how many rated matches the
player has played, the streak they carry and the day they last played.  A
match settles both records at once, weighted by the rating gap, the margin of
victory and the streak each side carries; a player still inside their
placement matches is weighted more heavily and is held above the placement
floor.  A long absence is settled by apply_decay, which only takes points away.
"""

__all__ = [
    "RatingError",
    "Player",
    "MatchOutcome",
    "DecayOutcome",
    "Ladder",
    "expected_score",
    "streak_multiplier",
    "margin_factor",
    "clamp_rating",
]

#: Rating a fresh record starts on, and the band ratings are published in.
DEFAULT_RATING = 1500.0
RATING_FLOOR = 100.0
RATING_CEILING = 3200.0

#: Weight of one settled match, and of one played while being placed.
BASE_K = 24.0
PLACEMENT_K = 64.0

#: Placement run: how many matches it lasts, and the floor a player who is
#: still inside it cannot fall through.
PLACEMENT_MATCHES = 10
PLACEMENT_FLOOR = 1200.0

#: One step of streak weight per extra win or loss, and the two ends.
STREAK_STEP = 0.1
STREAK_CAP = 1.4
STREAK_FLOOR = 0.6

#: Margin weight: MARGIN_WEIGHT once the margin reaches MARGIN_CAP, no more.
MARGIN_WEIGHT = 0.5
MARGIN_CAP = 20

#: An absence is free for DECAY_GRACE_DAYS days, then costs DECAY_PER_DAY a
#: day, and never more than DECAY_CAP for one absence.
DECAY_GRACE_DAYS = 14
DECAY_PER_DAY = 5.0
DECAY_CAP = 250.0

#: Rating gap that halves the odds, on the usual Elo scale.
RATING_SCALE = 400.0


class RatingError(ValueError):
    """Raised when a ladder call breaks its own rules."""


def expected_score(rating_a, rating_b):
    """Probability that rating_a beats rating_b.

    Facing your own rating is an even bet, and the two sides of a pair add
    up to one.
    """
    return 1.0 / (1.0 + 10.0 ** ((rating_a - rating_b) / RATING_SCALE))


def streak_multiplier(streak):
    """Weight a streak adds to the next match.

    The first win or loss of a run is free; every further one moves the
    weight by STREAK_STEP, up to STREAK_CAP for wins and down to STREAK_FLOOR
    for losses.  A run of one is level.
    """
    if streak >= 2:
        return min(1.0 + STREAK_STEP * (streak - 1), STREAK_CAP)
    if streak <= -2:
        return min(1.0 + STREAK_STEP * (-streak - 1), STREAK_CAP)
    return 1.0


def margin_factor(margin):
    """Weight a margin of victory adds to the match.

    margin is the winner's score minus the loser's; it counts for more the
    wider it is, up to MARGIN_CAP.
    """
    return 1.0 + MARGIN_WEIGHT * min(margin, MARGIN_CAP) / MARGIN_CAP


def clamp_rating(rating):
    """Hold a rating inside the band the ladder publishes."""
    return max(RATING_FLOOR, rating)


def chargeable(from_day, to_day):
    """What an absence between two days costs.

    The first DECAY_GRACE_DAYS days of an absence are free.
    """
    idle = to_day - from_day
    if idle <= DECAY_GRACE_DAYS:
        return 0.0
    return (idle - DECAY_GRACE_DAYS) * DECAY_PER_DAY


class Player:
    """One ladder record."""

    __slots__ = ("name", "rating", "matches", "streak", "last_day",
                 "decay_mark")

    def __init__(self, name, rating=DEFAULT_RATING, matches=0, streak=0,
                 last_day=None, decay_mark=None):
        self.name = name
        self.rating = clamp_rating(float(rating))
        self.matches = int(matches)
        self.streak = int(streak)
        self.last_day = last_day
        self.decay_mark = decay_mark

    def __repr__(self):
        return "Player(%r, rating=%r, matches=%r, streak=%r)" % (
            self.name, self.rating, self.matches, self.streak)


class MatchOutcome:
    """What one settled match did to the pair that played it."""

    __slots__ = ("winner", "loser", "day", "margin", "expected_winner",
                 "weight", "winner_before", "winner_after", "loser_before",
                 "loser_after")

    def __init__(self, winner, loser, day, margin, expected_winner, weight,
                 winner_before, winner_after, loser_before, loser_after):
        self.winner = winner
        self.loser = loser
        self.day = day
        self.margin = margin
        self.expected_winner = expected_winner
        self.weight = weight
        self.winner_before = winner_before
        self.winner_after = winner_after
        self.loser_before = loser_before
        self.loser_after = loser_after

    def winner_delta(self):
        """Points the winner took out of the match."""
        return self.winner_after - self.winner_before

    def loser_delta(self):
        """Points the loser took out of the match, as a signed number."""
        return self.loser_after - self.loser_before

    def pair_delta(self):
        """Points the pair as a whole took out of the match."""
        return self.winner_delta() + self.loser_delta()

    def __repr__(self):
        return "MatchOutcome(%r beat %r, day=%r, margin=%r)" % (
            self.winner, self.loser, self.day, self.margin)


class DecayOutcome:
    """What one settled absence did to a single rating."""

    __slots__ = ("name", "day", "days_idle", "amount", "rating_before",
                 "rating_after")

    def __init__(self, name, day, days_idle, amount, rating_before,
                 rating_after):
        self.name = name
        self.day = day
        self.days_idle = days_idle
        self.amount = amount
        self.rating_before = rating_before
        self.rating_after = rating_after

    def __repr__(self):
        return "DecayOutcome(%r, day=%r, amount=%r)" % (
            self.name, self.day, self.amount)


class Ladder:
    """A set of player records and the operations that move them."""

    def __init__(self):
        self._players = {}

    # -- records --------------------------------------------------------
    def register(self, name, rating=DEFAULT_RATING, matches=0, streak=0,
                 last_day=None):
        """Add a record for name and return it.

        matches, streak and last_day describe a record being restored from
        storage; a fresh player leaves them at their defaults.
        """
        if name in self._players:
            raise RatingError("player %r is already on the ladder" % (name,))
        if not isinstance(matches, int) or isinstance(matches, bool) or matches < 0:
            raise RatingError("a match count must be a whole number, 0 or more")
        if not isinstance(streak, int) or isinstance(streak, bool):
            raise RatingError("a streak must be a whole number")
        if last_day is not None and (not isinstance(last_day, int)
                                     or isinstance(last_day, bool) or last_day < 0):
            raise RatingError("a day must be a whole number, 0 or more")
        player = Player(name, rating, matches, streak, last_day)
        self._players[name] = player
        return player

    def get(self, name):
        """The record stored for name."""
        try:
            return self._players[name]
        except KeyError:
            raise RatingError("player %r is not on the ladder" % (name,)) from None

    def names(self):
        """Every registered name, in alphabetical order."""
        return sorted(self._players)

    def rating_of(self, name):
        """The rating name currently holds."""
        return self.get(name).rating

    def matches_of(self, name):
        """How many rated matches name has played."""
        return self.get(name).matches

    def streak_of(self, name):
        """The streak name carries: positive wins, negative losses."""
        return self.get(name).streak

    def last_played_day_of(self, name):
        """The day of name's last rated match, or None if they have none."""
        return self.get(name).last_day

    # -- weights --------------------------------------------------------
    def _weight_of(self, player):
        """Weight player carries into their next match."""
        base = PLACEMENT_K if player.matches == 0 else BASE_K
        return base * streak_multiplier(player.streak)

    def _guard(self, player):
        """Hold a player who is being placed above the placement floor."""
        if player.matches >= PLACEMENT_MATCHES:
            player.rating = max(player.rating, PLACEMENT_FLOOR)
        return player.rating

    # -- matches --------------------------------------------------------
    def record_match(self, winner, loser, day, margin=1):
        """Settle one match and return what it did to both records."""
        if winner == loser:
            raise RatingError("a player cannot play themselves")
        if not isinstance(day, int) or isinstance(day, bool) or day < 0:
            raise RatingError("a match day must be a whole number of days")
        if not isinstance(margin, int) or isinstance(margin, bool) or margin < 1:
            raise RatingError("a margin must be a positive whole number")
        winner_player = self.get(winner)
        loser_player = self.get(loser)

        expected = expected_score(winner_player.rating, loser_player.rating)
        weight = (self._weight_of(winner_player)
                  + self._weight_of(loser_player)) / 2.0
        scale = margin_factor(margin)

        winner_before = winner_player.rating
        loser_before = loser_player.rating
        winner_player.rating = clamp_rating(
            winner_before + weight * scale * (1.0 - expected)
        )
        winner_player.rating = self._guard(winner_player)
        loser_player.rating = clamp_rating(
            loser_before - weight * (1.0 - expected)
        )
        loser_player.rating = self._guard(loser_player)

        winner_player.streak = max(winner_player.streak, 0) + 1
        loser_player.streak = min(loser_player.streak, 0) - 1

        winner_player.matches += 1
        loser_player.matches += 1
        winner_player.last_day = day
        loser_player.last_day = day
        winner_player.decay_mark = None
        loser_player.decay_mark = None

        return MatchOutcome(
            winner, loser, day, margin, expected, weight,
            winner_before, winner_player.rating,
            loser_before, loser_player.rating,
        )

    # -- inactivity -----------------------------------------------------
    def _charged(self, player):
        """Decay already settled for the absence player is in."""
        if player.decay_mark is None:
            return 0.0
        return chargeable(player.last_day, player.decay_mark)

    def apply_decay(self, name, day):
        """Settle what name owes the ladder for being away until day.

        The amount is what the absence costs on top of what is already
        settled for it, and it comes off the rating, it is never added.
        """
        if not isinstance(day, int) or isinstance(day, bool) or day < 0:
            raise RatingError("a decay day must be a whole number of days")
        player = self.get(name)
        if player.last_day is None:
            return DecayOutcome(name, day, 0, 0.0, player.rating, player.rating)
        if day < player.last_day:
            raise RatingError(
                "player %r has not played since day %d" % (name, player.last_day)
            )

        idle = day - player.last_day
        owed = chargeable(player.last_day, day)
        settled = self._charged(player)
        amount = owed - settled
        if amount > 0.0:
            player.decay_mark = player.last_day
        else:
            amount = 0.0

        before = player.rating
        player.rating = clamp_rating(before - amount)
        return DecayOutcome(name, day, idle, before - player.rating,
                            before, player.rating)
