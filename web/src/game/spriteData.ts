// 픽셀 스프라이트 그림 (데스크톱 game/sprites.py에서 그대로 옮긴 데이터).
// 글자 하나 = 한 칸: '.' 빈칸, n/N 나라 색(밝은/어두운), 나머지는 pal 색.
export const SPRITES = {
 "outline": [
  22,
  18,
  26
 ],
 "pal": {
  "s": [
   232,
   188,
   148
  ],
  "d": [
   52,
   42,
   44
  ],
  "g": [
   184,
   188,
   198
  ],
  "G": [
   120,
   124,
   136
  ],
  "w": [
   156,
   106,
   62
  ],
  "W": [
   100,
   66,
   40
  ],
  "y": [
   226,
   198,
   96
  ],
  "Y": [
   178,
   146,
   60
  ],
  "r": [
   160,
   158,
   160
  ],
  "R": [
   104,
   102,
   112
  ],
  "f": [
   70,
   130,
   58
  ],
  "F": [
   42,
   86,
   44
  ],
  "c": [
   204,
   178,
   128
  ]
 },
 "units": [
  [
   [
    "..gg.g",
    "..ss.w",
    ".nnnnw",
    ".nnn.w",
    "..dd..",
    "..d.d."
   ],
   [
    "..gg.g",
    "..ss.w",
    ".nnnnw",
    ".nnn.w",
    "..dd..",
    ".d..d."
   ]
  ],
  [
   [
    "..nn..",
    "..ss.W",
    ".cnccW",
    ".ccc.W",
    "..dd..",
    "..d.d."
   ],
   [
    "..nn..",
    "..ss.W",
    ".cnccW",
    ".ccc.W",
    "..dd..",
    ".d..d."
   ]
  ]
 ],
 "buildings": {
  "0": [
   "....NNNNN....",
   "...NnnnnnN...",
   "..NnnnnnnnN..",
   ".NnnnnnnnnnN.",
   "NNNNNNNNNNNNN",
   ".wwwwwwwwwww.",
   ".wdwwwdwwwdw.",
   ".wdwwwdwwwdw.",
   ".wwwwwWWwwww.",
   ".WWWWWWWWWWW."
  ],
  "1": [
   "...NN......",
   "..NnnN.y.y.",
   ".NNNNNNyyyy",
   ".wwwww.yYy.",
   ".wwdww.yyyy",
   ".wwdww.YyYy",
   "WWWWWWWWWWW"
  ],
  "2": [
   "...NN......",
   "..NnnN.....",
   ".NNNNNN....",
   ".wwwww.WWW.",
   ".wwdww.wyw.",
   ".wwdwwWWWWW",
   "......wywyw"
  ],
  "3": [
   ".n.........",
   ".nn........",
   ".d...rr....",
   ".d..rrrR...",
   ".drrrRrrr..",
   "rrRrrrrRrr.",
   "RRRRRRRRRRR"
  ],
  "4": [
   ".dnn...",
   ".dn....",
   ".d.....",
   "rrrrrrr",
   "rRrRrRr",
   ".rrrrr.",
   ".rrdrr.",
   ".rrrrr.",
   ".rRrrr.",
   ".rrrrr.",
   ".rrdrr.",
   ".rrdrr.",
   "RRRRRRR"
  ],
  "5": [
   "...NNNN....",
   "..NnnnnN...",
   ".NNNNNNNN..",
   ".wwwwwww...",
   ".wwdwwdw...",
   "WWWWWWWWWWW",
   "W.W.W.W.W.W"
  ]
 },
 "ships": {
  "ferry": [
   "...n....",
   "...nn...",
   "...Wnn..",
   "WwwwwwwW",
   ".WWWWWW."
  ],
  "warship": [
   "......n......",
   ".....Wnn.....",
   "..nn.Wnnnn...",
   ".nnn.Wnnnnn..",
   "WWWWWWWWWWWWW",
   "WwdwwdwwdwwwW",
   ".WWWWWWWWWWW."
  ]
 },
 "sites": {
  "0": [
   "y.y.y",
   "yyyyy",
   ".yYy.",
   "..f..",
   "..f.."
  ],
  "1": [
   "..f..",
   ".fff.",
   "ffFff",
   ".fFf.",
   "..W.."
  ],
  "2": [
   "..r..",
   ".rrr.",
   "rrRrr",
   "rRrrR",
   "RRRRR"
  ]
 }
} as const;
