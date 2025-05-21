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
LLAMA_MODEL = None  # Global reference to loaded LLaMA model

def GetDefaultProvider():
    """Returns default AI provider and API key based on available API keys in environment.
    
    Returns:
        tuple[str|None, str|None]: A tuple containing:
            - provider: 'gemini', 'openai', or 'llama' if respective key/path is set, None if no keys
            - api_key: The corresponding API key if found, None otherwise
    """
    # Check for LLaMA model path first as it's local
    llama_path = os.getenv('LOGICA_LLAMA_MODEL_PATH')
    if llama_path and os.path.exists(llama_path):
        return "llama", llama_path
    
    gemini_key = os.getenv('LOGICA_GEMINI_API_KEY')
    if gemini_key:
        return "gemini", gemini_key
    
    openai_key = os.getenv('LOGICA_OPENAI_API_KEY')
    if openai_key:
        return "openai", openai_key
    
    return None, None

def InitializeAI(provider=None):
    """Initializing AI API by setting the API key."""
    global PROVIDER, LLAMA_MODEL
    
    # If no provider specified, try to get default from environment
    if provider is None:
        provider, api_key = GetDefaultProvider()
    # If provider specified, verify and get the API key
    elif provider == "gemini":
        api_key = os.getenv('LOGICA_GEMINI_API_KEY')
        if not api_key:
            print(f"Warning: {provider} specified but no API key found in environment")
            provider = None
    elif provider == "openai":
        api_key = os.getenv('LOGICA_OPENAI_API_KEY')
        if not api_key:
            print(f"Warning: {provider} specified but no API key found in environment")
            provider = None
    elif provider == "llama":
        api_key = os.getenv('LOGICA_LLAMA_MODEL_PATH')
        if not api_key or not os.path.exists(api_key):
            print(f"Warning: {provider} specified but no valid model path found in environment")
            provider = None
        
    if provider is None:
        print("\nPlease choose the AI provider:")
        print("1. OpenAI (gpt-3.5-turbo)")
        print("2. Google Gemini (gemini-2.0-flash)")
        print("3. Local LLaMA")
        choice = input("Enter your choice (1, 2, or 3): ").strip()
        
        if choice == "1":
            provider = "openai"
        elif choice == "2":
            provider = "gemini"
        elif choice == "3":
            provider = "llama"
        else:
            raise ValueError("Invalid choice. Please select 1 for OpenAI, 2 for Gemini, or 3 for LLaMA.")
    
    PROVIDER = provider
    
    if PROVIDER == "openai":
        import openai
        if not openai.api_key:
            openai.api_key = api_key
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
        if not api_key:
            print()
            print('Google Gemini API will be used to run Logica Intelligence function.')
            print('No key provided in the environment variable LOGICA_GEMINI_API_KEY.')
            api_key = getpass.getpass('Please provide Gemini API key to run Intelligence function:')
            if not api_key:
                raise Exception('Intelligence function could not obtain Gemini API key.')
            genai.configure(api_key=api_key)
        else:
            genai.configure(api_key=api_key)
    
    elif PROVIDER == "llama":
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError("Please install llama-cpp-python first: pip install llama-cpp-python")
        
        if not api_key:
            print()
            print('Local LLaMA will be used to run Logica Intelligence function.')
            print('No model path provided in the environment variable LOGICA_LLAMA_MODEL_PATH.')
            model_path = input('Please provide the path to your LLaMA model file (.gguf): ').strip()
            if not model_path or not os.path.exists(model_path):
                raise Exception('Invalid model path or model file does not exist.')
            api_key = model_path
        
        print("Loading LLaMA model... This might take a few moments.")
        LLAMA_MODEL = Llama(model_path=api_key)
    else:
        assert False, "Unknown provider: %s" % PROVIDER

def Intelligence(command):
    """Executing command on AI API and returning the response."""
    global intelligence_executed
    global PROVIDER, LLAMA_MODEL

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
        
    elif PROVIDER == "llama":
        response = LLAMA_MODEL.create_completion(
            prompt=command,
            max_tokens=512,
            temperature=0.7,
            top_p=0.95,
            stop=["</s>", "\n\n"]
        )
        return response['choices'][0]['text']