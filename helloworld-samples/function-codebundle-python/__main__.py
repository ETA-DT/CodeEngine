# ======================================================= #
#  IBM Cloud Code Engine - Functions-as-a-Service Sample  #
#                                                         #
#  __main.py__ (Python sample function)                   #
#                                                         #
#  This sample code uses an external module "lorem"       #
#  to generate an arbitrary result message. IBM code      #
#  engine functions code with references to external      #
#  modules have to be deployed as code-bundles.           # 
#
#  This sample shows how to access URL parameters in a    #
#  function.                                              #
#                                                         #
#  This sample shows how an external reference is coded   #
#  in the source file (__main__.py) and how the modul     #
#  is referenced in the requirements.txt.                 #
#                                                         #
# ======================================================= #

##
 # import the referenced "lorem" module 
from lorem_text import lorem
import tm1py
import subprocess
import sys
import json
import os

##
 # The `main` function is the entry-point into the function.
 # 
 # A function can define multiple functions, but it needs to
 # have one dedicated 'main' function, which will be called
 # by the runtime.
 # 
 # The 'main' function has one optional argument, which 
 # carries all the parameters the function was invoked with.
 # 
 # Those arguments are dynamic and can change between 
 # function invocations. 
 # 
 # Additionally, a function has access to some 
 # predefined and also user-defined environment variables.
 #  
# def main(params):
#      words = 10

#      return {
#           # specify headers for the HTTP response
#           # we only set the Content-Type in this case, to 
#           # ensure the text is properly displayed in the browser
#           "headers": {
#               "Content-Type": "text/plain;charset=utf-8",
#           },
          
#           ## use the text generator to create a response sentence
#           #  with 10 words
#           "body": lorem.words(words),
#       }

from TM1py.Services import TM1Service

    # PA credentials
    credentials = {
    "address": "91.236.254.119",
    "port": 5029,
    "user": "erwan.tang",
    "password": "Datatilt2021",
    "ssl":False,
    "decode_b64"=False}


    # Extract Parameter from watsonx Assistant Trigger
    parameter = {
        "organization": params.get('organization', ''),
        "channel": params.get('channel', ''),
        "product": params.get('product', ''),
        "month": params.get('month', ''),
        "year": params.get('year', ''),
        "units": params.get('units', 0)}

    try:
        with TM1Service(address=credentials["address"], port=credentials["port"], user=credentials["user"], password=credentials["password"], ssl=False, namespace=credentials["namespace"]) as tm1:
            # Cellset = Data Record written into PA
            cellset = {
                ("BUDG_VC","2025.01","Finlande","Coûts Commerciaux"): 9999}

            # Write values into PA Cube using TM1py
            tm1.cubes.cells.write_values("00.Ventes", cellset)
            response = {
                "status": "success",
                "message": "Cell updated successfully",
                "parameters": parameter}
            return {
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps(response)}
    except Exception as e:
        error_message = f"Error occurred: {str(e)}"
        if hasattr(e, 'args') and e.args:
            try:
                error_details = json.loads(e.args[0])
                error_message = f"{error_message}. Details: {error_details}"
            except (json.JSONDecodeError, TypeError):
                pass
        response = {
            "status": "error",
            "message": error_message
        }
        return {
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(response)}
# Optional:
#   If you used a function name different from 'main', make
#   the function known under the 'main' symbol to the 
#   runtime, so it can be invoked.
#
#   Example:
#
#   def my_main_func_with_another_name(params) {
#     ...
#   }
#   ...
#   main = my_main_func_with_another_name
