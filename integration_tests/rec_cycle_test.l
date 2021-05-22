# Recursive cycle test.

@Engine("sqlite");                                                                                                                
                                                                                                                                  
@RecursiveDepth(A, 2);                                                                                                            
A(x) :- B(x), C(x);                                                                                                               
                                                                                                                                  
B(x) :- D(x);                                                                                                                     
C(x) :- E(x);                                                                                                                     
                                                                                                                                  
D(x) :- F(x);                                                                                                                     
E(x) :- F(x);                                                                                                                     
                                                                                                                                  
F(x) :- G(x);                                                                                                                     
                                                                                                                                  
G(x) :- x == "g";                                                                                                                 
                                                                                                                                  
F(x) :- A(x);                                                                                                                     
                                                                                                                                  
H(x) :- I(x);                                                                                                                     
I("i");                                                                                                                           
                                                                                                                                  
J(x) :- C(x);                                                                                                                     
                                                                                                                                  
K(x) :- B(x);                                                                                                                     
L(x) :- K(x);                                                                                                                     
K(x) :- L(x);                                                                                                                     
L("l");        

@OrderBy(Test, "col0");
Test(x) :- A(x) | L(x) | H(x);