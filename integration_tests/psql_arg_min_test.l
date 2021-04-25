@Engine("psql");

Employee(dep: "Eng", name: "John", vacation_days: 8);
Employee(dep: "Eng", name: "James", vacation_days: 4);
Employee(dep: "Eng", name: "Matthew", vacation_days: 2);
Employee(dep: "Eng", name: "Jeremy", vacation_days: 5);
Employee(dep: "Sales", name: "Evan", vacation_days: 7);

PersonWithLeastDays(dep:,
                    person? ArgMin= name -> vacation_days) distinct :-
  Employee(dep:, name:, vacation_days:);

Test := PersonWithLeastDays();

