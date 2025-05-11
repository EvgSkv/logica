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

import getpass
import os

intelligence_executed = False
PROVIDER = None  # Will be set during first execution

def InitializeAI(provider=None):
    """Initializing AI API by setting the API key."""
    global PROVIDER
    
    if provider is None:
        print("\nPlease choose the AI provider:")
        print("1. OpenAI (gpt-3.5-turbo)")
        print("2. Google Gemini (gemini-2.0-flash)")
        choice = input("Enter your choice (1 or 2): ").strip()
        
        if choice == "1":
            provider = "openai"
        elif choice == "2":
            provider = "gemini"
        else:
            raise ValueError("Invalid choice. Please select 1 for OpenAI or 2 for Gemini.")
    
    PROVIDER = provider
    
    if PROVIDER == "openai":
        import openai
        if not openai.api_key:
            openai.api_key = os.getenv('LOGICA_OPENAI_API_KEY')
            if not openai.api_key:
                print()
                print('OpenAI API will be used to run Logica Intelligence function. '
                      'Logica engine does not have any throttling for it. '
                      'Please be mindful that naturally OpenAI project which key you provide '
                      'will be charged by OpenAI.')
                print('No key provided in the environment variable LOGICA_OPENAI_API_KEY.')  
                openai.api_key = getpass.getpass('Please provide OpenAI API key to run '
                                               'Intelligence function:')
                if not openai.api_key:
                    raise Exception('Intelligence function could not obtain openai.api_key.')
    
    elif PROVIDER == "gemini":
        import google.generativeai as genai
        if not os.getenv('LOGICA_GEMINI_API_KEY'):
            print()
            print('Google Gemini API will be used to run Logica Intelligence function.')
            print('No key provided in the environment variable LOGICA_GEMINI_API_KEY.')
            api_key = getpass.getpass('Please provide Gemini API key to run Intelligence function:')
            if not api_key:
                raise Exception('Intelligence function could not obtain Gemini API key.')
            genai.configure(api_key=api_key)
        else:
            genai.configure(api_key=os.getenv('LOGICA_GEMINI_API_KEY'))

def Intelligence(command):
    """Executing command on AI API and returning the response."""
    global intelligence_executed
    global PROVIDER

    if not intelligence_executed:
        InitializeAI()
    intelligence_executed = True

    if PROVIDER == "openai":
        import openai
        client = openai.OpenAI(api_key=openai.api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "user",
                    "content": command
                }
            ],
            temperature=1,
            max_tokens=512,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )
        return response.choices[0].message.content
    
    elif PROVIDER == "gemini":
        import google.generativeai as genai
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(command)
        return response.text