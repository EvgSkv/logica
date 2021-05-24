# Small part of Queen Victoria descended tree.
# Source:
# https://en.wikipedia.org/wiki/Royal_descendants_of_Queen_Victoria_and_King_Christian_IX

Parent("Queen Victoria", "King Edward VII");
Parent("Queen Victoria", "Prince Leopold");
Parent("King Edward VII", "King George V");
Parent("King Edward VII", "Maud of Wales");
Parent("King George V", "King George VI");
Parent("King George VI", "Queen Elizabeth II");
Parent("Queen Elizabeth II", "Prince Charles");
Parent("Queen Elizabeth II", "");
Parent("Queen Victoria", "Prince Arthur");
Parent("Prince Arthur", "Margaret Princess of Sweden");
Parent("Margaret Princess of Sweden",
       "Ingrid Queen of Denmark");

Grandparent(a, c) :- Parent(a, b), Parent(b, c);