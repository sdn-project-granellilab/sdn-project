

class Queue:
    def __init__(self, min_bw:int,max_bw:int) -> None:
        self.min_rate=str(min_bw)
        self.max_rate=str(max_bw)
    def rate_dict(self):
        return{
            'max-rate':self.max_rate,
            'min-rate':self.min_rate
        }