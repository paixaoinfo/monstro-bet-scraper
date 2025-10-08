import asyncio
from playwright.async_api import async_playwright
import json
import os

# Define the Firebase credentials directly in the script for this temporary verification
firebase_config = {
  "type": "service_account",
  "project_id": "monstro-bet-app",
  "private_key_id": "3d7e9f179fc226fc9685433689c7c2f7629ae945",
  "private_key": """-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQCx3tpiu0q74MeW\nmBTIss+PYDIrxZizStU3xMVAYrQsHxfbHv2zRXCqJ3tkhL+lZ3ZAr983KfLwSgKv\nYi15VDwTyBRknHxMns/H7qxTbRSP5GGz1b5aeMvTR/PL2j2+qbJ1AA1iskIcm1Nn\n0z8JuPJBp6628dC6ZVDUgvifFc8oKMytDvc7puYY8OzJKsk5q5LTRSEVzoMF5aG3\nOaGaIRoSf5YyX6cdpZciFMp9bjo1PpbOPBTcYix0RW3OkwgGNVcxfnUasUpXkKhl\nT4azjbGnRyWxsHlv8JOLIk3VRRKBWuzNofjQn4iEXN6UObt2NSTuK1YGl5M4U3lc\nNvd3tiC9AgMBAAECggEAD5ilWIPorSmsBonmRKTdK0q5i3oDhjEZGg9AZoFhH/9H\n9bg1cas0kk7s9GbpcQTt6wUg0vL0MNqkeqFmsF1Q+UERfLL1+TfxqyvD43rMk0No\nx76FtuQhpzCHcYf84wN5OOYcxlswDdcWzKNKwzz6zQP5f2Qbs8RfforPZw+f/vrT\nSCiG0OMr09gBsihohGegiG/uHDV5kFL9raH155mc5MBA7VRjXYZXhgIvHfF+DmXv\nm1+TPxsdevAnkGU9QeVODFowgor4axEQUswctAKCUTOTESfvCt99DavUBrn++rgU\n5LiTEwRqQG1LlzjWyVssStOdiwnimJSIWXqSUNKWNwKBgQDppi128m1RpBf4NPfT\nej8Rhbd1BhGGk62sbgzebkfc3WpcF54S9jvjE6nw80cSrn7smXAmrMRCS3zc62W9\nIIBM1WiRpmNSWeaC3Gs+cX3qATdJquiq7fTv2HJx3LsQQH1Epwv3aQNelxXrlMUY\nXo3QgOHX8JZzkSXIBepZmDARYwKBgQDC4rc5s8Oa3uz6c7fizPAgoQojtqi0STV8\nTtONOEyZQFjjhSWmJ9Ou1Bf7uajQWWBDZV538f1bVVOJOQgFSKAJxgjMGbFs/y4a\n8DQRuY3zL5EbJFawM2twJdncKzwVbA2hhZDHtboWsFUMUrh2W02I8zR+WKzJYr7n\nIRyJDR+vXwKBgAUEI0+9bqllC3qxsGxi4H3A0Cp8Ad5Qx1a/WhlgZryQKFtnymX/\n0VNTtb9NicYV5vWvaZ/674+4zSp1B08jJn3/yuntl45KDc/baZYCm8BtXEGBoNMi\nnrKThAl7wqxbphTWPUSHhaH/PmI7ZGvcg9DpI3AeYyyB/jyoG9rmkImfAoGAGsox\np8P3YqW8a91WbN4BMGsSysAERuw9Zv4rBKG1neeDkJswBrw41DKhrV/jPejbW8hm\niRSB4HlFR3rIiHloTo+ji/MIOdSGUPuuHLWmNsTWLKX9KLGY1kzNuv9SfhthcE+9\nDEcF8rKArnX8l4CLkwTjtW6ZKgHh/kHF+20Lav8CgYBdcKCHf9TVHWFTxCmqLD/a\ngJrXSk0EVObWOmOU/UPcbuz2wmKxFCuTs2mpeyXSnCJoQqUH7r/vFcI8yYCoEZGh\n+1k8twIVkmzLYXTEjQhq6Y3Udp/Gs3HtbUkdJnWPhZaXo0/7lMD9rBNtFQDMWMcY\nW+WMFepXkMRluv2ZL1AKwQ==\n-----END PRIVATE KEY-----\n""",
  "client_email": "firebase-adminsdk-fbsvc@monstro-bet-app.iam.gserviceaccount.com",
  "client_id": "102242732979540066512",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40monstro-bet-app.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Listen for all console events and print them
        page.on("console", lambda msg: print(f"BROWSER LOG: {msg.text}"))

        # Inject Firebase config into the page
        await page.add_init_script(f"""
            window.__firebase_config = `{json.dumps(firebase_config)}`;
        """)

        file_path = os.path.abspath("bet.html")
        await page.goto(f"file://{file_path}")

        print("Initial page loaded. Clicking 'Carregar Todos os Jogos'...")
        await page.click("#searchBtn")

        try:
            print("Waiting for match cards to be rendered...")
            await page.wait_for_selector(".card-enter", timeout=10000) # Reduced timeout for faster failure

            print("Match cards found. Taking final screenshot.")
            await page.screenshot(path="jules-scratch/verification/verification.png")
        except Exception as e:
            print(f"Verification script failed: {e}")
            await page.screenshot(path="jules-scratch/verification/verification_error.png")


        await browser.close()
        print("Verification script finished.")

if __name__ == "__main__":
    asyncio.run(main())