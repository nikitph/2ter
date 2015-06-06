__author__ = 'Omkareshwar'


class Player:
    name = ''
    dots = 0
    ones = 0
    twos = 0
    threes = 0
    fours = 0
    sixes = 0
    balls = 0
    out = False
    how = ''
    bowler = ''
    keeper = ''
    catcher = ''
    runout = False
    OnStrike = False

    def __init__(self, name):
        self.name = name

    def total(self):
        to = self.ones + 2 * self.twos + 3 * self.threes + 4 * self.fours + 6 * self.sixes
        return to

    def dismissed(self, how, who1, who2=None):
        self.out = True
        if how == 'runout':
            self.runout = True
        elif how == 'catch':
            self.bowler = who1
            self.catcher = who2
        elif how == 'bowled':
            self.bowler = who1
        elif how == 'stumped':
            self.bowler = who1
            self.keeper = who2
        return True

    def update_runs(self, run):
        if True:
            self.balls += 1
            if run == 0:
                self.dots += 1
            elif run == 1:
                self.ones += 1
            elif run == 2:
                self.twos += 1
            elif run == 3:
                self.threes += 1
            elif run == 4:
                self.fours += 1
            elif run == 6:
                self.sixes += 1

    def update_strike(self, strike):
        self.OnStrike = strike

    def return_runs(self):
        """

        :rtype : dict
        """
        runs = [self.name,
                self.dots,
                self.ones,
                self.twos,
                self.threes,
                self.fours,
                self.sixes,
                self.total(),
                self.balls]
        return runs
