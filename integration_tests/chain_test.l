#
# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Example of a test for a chain with ground-only predicates.
import integration_tests.chain.A;  # To mock.
import integration_tests.chain.C;  # To connect.
import integration_tests.chain.D;  # To connect.
import integration_tests.chain.F;  # To test.

# Mocking data.
MockA("mock_data");

# Fixing chain broken due to lack of files.
# Note that since D is not defined (only grounded) in chain.ydg we can not
# import it. But it lives as-is in global namespace, so we can directly mock it.
# TODO: This is probably not ideal and we need to limit ground-only
# predicates to their file.
MockD(x) :- C(x);

# Testing.
TestF := F(A: MockA, D: MockD);
