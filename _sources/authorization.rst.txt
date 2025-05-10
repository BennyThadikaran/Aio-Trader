=============
Authorization
=============


Kite login and authorization
----------------------------

All arguments are optional. It defaults to Kite web login if no arguments are provided. You will be required to enter your credentials via terminal user input.

Once authorization is complete, the token is set. You can access them as 

- :py:obj:`kite.enctoken` - For Kite web login 
- :py:obj:`kite.access_token` - For KiteConnect login

These can be stored or saved and reused on the next run. You can pass the token to the Kite class during initialization.

**For Kite web login**, :py:obj:`Kite.authorize` takes the following optional parameters:

- :py:obj:`user_id`: Kite Web user-id
- :py:obj:`password`: Kite Web login password
- :py:obj:`twofa`: string or callable function that returns OTP

To generate OTP you can use a package like `pyotp <https://pypi.org/project/pyotp/>`_, just pass :py:obj:`totp.now` to **twofa** argument.

.. code:: python

    # Kite Web Login
    async with Kite(enctoken=enctoken) as kite:
      await kite.authorize(
          user_id=user_id,
          password=pwd,
          twofa=pyotp.TOTP('TOTP_STRING').now, # dont invoke now()
      )

**For KiteConnect login**, :py:obj:`Kite.authorize` takes the following optional parameters:

- :py:obj:`request_token` : KiteConnect request_token 
- :py:obj:`api_key`: KiteConnect API key
- :py:obj:`secret`: KiteConnect API secret

.. code:: python

    # KiteConnect login
    async with Kite(access_token=access_token) as kite:
      await kite.authorize(
          request_token=request_token,
          api_key=api_key,
          secret=secret,
      )

KiteFeed requires the following optional arguments

**For Kite Web:**

- :py:obj:`user_id`: Kite Web user-id
- :py:obj:`enctoken`: enctoken obtained from Kite Web Login

**For KiteConnect:**

- :py:obj:`api_key`: Kite Web user-id
- :py:obj:`access_token` : access_token obtained from KiteConnect login

Authorization Flow
~~~~~~~~~~~~~~~~~~

1. On running :py:obj:`Kite.authorize`, it first checks if :py:obj:`enctoken` or :py:obj:`access_token` was set during initialization. 
    - If yes, the authorization headers are updated, and the class is ready to make API requests. 
2. If :py:obj:`request_token` and :py:obj:`secret` are provided, proceed with KiteConnect login. Once the :py:obj:`access_token` is received, set the authorization headers.
3. For Kite Web login, :py:obj:`enctoken` is stored in cookies. Check if the cookie file exists and has not expired. If yes, load the :py:obj:`enctoken` and update headers.
4. If no cookie file exists or has expired, proceed with Kite Web login. Once the :py:obj:`enctoken` is received:
    - Set the cookie expiry for the end of the day.
    - Save the cookie to file
    - Update the authorization headers with :py:obj:`enctoken`

Dhan login and authorization
----------------------------

Authorization with Dhan is simple. Pass the `client_id` and `access_token` (provided during app registration) to the constructor.

.. code:: python

   async with Dhan(client_id="client_id", access_token="access_token") as dhan:
        holdings = await dhan.get_holdings()
  
Fyers login and authorization
-----------------------------

Fyers requires generating an app at https://myapi.fyers.in/ to get the APP id and secret id.

You must also provide the redirect url, which is required during the authorization.

.. code:: python

  from aio_trader.fyers import FyersAuth


  async def main():
      # STEP 1
      auth = FyersAuth(
          client_id="client_id",
          redirect_uri="redirect_uri",
          secret_key="secret_key",
          state="OPTIONAL random string",
      )

      # Open the below url in a browser and login
      # On successful login you will be redirected to the redirect_uri
      # with the auth_token and state in url parameters
      url = auth.generate_authcode()

      # STEP 2: Use the auth_token received in previous step
      auth_token = "auth_token"

      data = await auth.generate_token(auth_code=auth_token)

      if "access_token" not in data:
          print("Failed to get access_token")
          await auth.close()

      access_token = data["access_token"]

Use the access token received to make requests.

.. code:: python

   async with Fyers(client_id="client_id", token="access_token") as fyers:
        await fyers.get_profile()
