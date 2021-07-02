# Testing import_root parser parameter.
# Test needs to run with import_root=integration_tests/import_tests, where
# canada.l is located.

import canada.ProductCanada;

@Engine("sqlite");
Test(..r) :- ProductCanada(..r);