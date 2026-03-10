import requests
from rich import print
import os

OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")


def ask_llm(prompt):

    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": "llama3",
            "prompt": prompt,
            "stream": False
        }
    )

    return response.json()["response"]


def main():

    print("[green]Local Ollama AI Agent Started[/green]")

    while True:

        user_input = input("\nYou: ")

        if user_input in ["exit", "quit"]:
            break

        response = ask_llm(user_input)

        print("\nAI:")
        print(response)


if __name__ == "__main__":
    main()
