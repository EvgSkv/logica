#
# Copyright 2021 Google LLC
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

# Testing SQLite file read, write and string join.

@Engine("sqlite");

Test(result) :-
  filename == "/tmp/sqlite_file_test_data.txt",
  WriteFile(filename, content: input_array) == "OK",
  input_array List= (x * 2 :- x in Range(10)),
  read_data == ReadJson(filename),
  result_array List= (x :- x in read_data, x > 10),
  result == Join(result_array, "/");