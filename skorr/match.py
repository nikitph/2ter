__author__ = 'Omkareshwar'

from player import Player


class Match:
    team_one = {}
    team_two = {}

    def __init__(self, team1, team2):
        for i in team1:
            playr = Player(i)
            self.team_one[i] = playr
        for j in team2:
            pl = Player(j)
            self.team_two[j] = pl
        pass

    def get_player(self, name):
        return self.team_one.get(name)