#!/usr/bin/python
#
# Copyright 2023 Google LLC
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

import os

intelligence_executed = False


def InitializeOpenAI():
  """Initializng OpenAI api by setting the API key."""
  import openai
  print()
  print('OpenAI API will be used to run Logica Intelligence function. '
        'Logica Engine does not have any throttling for it. '
        'Please be mindful that naturally OpenAI project which key you provide '
        'will be charged by OpenAI.')

  if not openai.api_key:
    print('Trying to retrieve OpenAI API key to run Intelligence function from '
          'environment variable LOGICA_OPENAI_API_KEY.')
    openai.api_key = os.getenv('LOGICA_OPENAI_API_KEY')
    if not openai.api_key:
      print('No key provided in the environment variable.')  
      openai.api_key = input('Please provie OpenAI API key to run '
                             'Intelligence function:')
      if not openai.api_key:
        raise Exception('Intelligence function could not obtain openai.api_key.')


def Intelligence(command):
  """Executing command on OpenAI API and returning the response."""
  # Imporing only if needed, so that installation is not required.
  import openai
  if not intelligence_executed or not openai.api_key:
    InitializeOpenAI()

  response = openai.Completion.create(
    model="text-davinci-003",
    prompt = command,
    temperature=0.7,
    max_tokens=512,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0
  )

  response_text = response.choices[0].text.strip()

  return response_text