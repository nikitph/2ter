__author__ = 'Omkareshwar'

from player import Player


class Match:
    team_one = {}
    team_two = {}
    overs = 0

    def __init__(self, team1, team2):
        for i in team1:
            playr = Player(i)
            self.team_one[i] = playr
        for j in team2:
            pl = Player(j)
            self.team_two[j] = pl
        pass

    def get_player(self, name, team):
        """

        :rtype : Player
        """
        if team ==1:
            return self.team_one.get(name)
        else:
            return self.team_two.get(name)

    def get_all_players(self, team):
        if team == 1:
            return self.team_one
        elif team == 2:
            return self.team_two

    def get_next_player(self, index, team):
        if team ==1:
            player_list = self.team_one.keys()
        else:
            player_list = self.team_two.keys()
        return player_list[index]