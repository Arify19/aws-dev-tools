import boto3
import json
import os
import paramiko
import random
import time
import uuid
from dotenv import load_dotenv

#Load env variables from file ".env"
load_dotenv("../.env")

#Load keys from environment variables
access_key = os.getenv("AWS_ACCESS_KEY_ID")
secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
assert (access_key is not None and secret_key is not None), "Error Importing AWS credentials"

#Load ec2 configurations
json_file = open("config.json")
ec2_config = json.load(json_file)
json_file.close()
key_filename = ec2_config["KeyFilename"]
image_id = ec2_config["ImageId"]
min_instances = ec2_config["MinInstances"]
max_instances = ec2_config["MaxInstances"]
instance_type = ec2_config["InstanceType"]

#Initialize an AWS session using credentials
session = boto3.Session(
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
)

# Initialize an EC2 client
client = session.client("ec2")

# Initialize an EC2 resource client
ec2 = session.resource("ec2")

#Create new keypair file
if os.path.exists(key_filename):
    os.remove(key_filename)
keyfile = open(key_filename, 'w')
 
#Create AWS keypair data
keypair_id = 'ec2-keypair' + str(uuid.uuid1())
ec2_keypair = ec2.create_key_pair(KeyName=keypair_id)
keypair_data = str(ec2_keypair.key_material)

#write keypair data to our file
keyfile.write(keypair_data)
keyfile.close()

#Change key permissions as required by AWS ssh policies
os.chmod(key_filename, 400)


# Create an EC2 VM in AWS
print("Creating instance...")
instance = ec2.create_instances(
    ImageId = image_id,
    MinCount = min_instances,
    MaxCount = max_instances,
    InstanceType = instance_type,
    KeyName= keypair_id
)

# Only one instance should be returned, so we take the 0th element
instance = instance[0]

# Obtain the instance ID
instance_id = instance.id
print("original instance id: %s" % instance_id)

# Wait for the instance to completely finish starting
print("Waiting for instance to start...")
instance.wait_until_running()
print("instance started")

# Use AWS Client to retrieve our VM Information
# This is done because the `instance` object returned by `create_instances()` doesnt' contain any information besides the instance id
instance_data = client.describe_instances(
    InstanceIds=[instance_id]
)

# There should only be 1 instance returned because we filtered by the ID
instance_data = instance_data["Reservations"][0]["Instances"][0]

print("instance id: %s" % instance_data["InstanceId"])
print("instance ip address: %s" % instance_data["PublicIpAddress"])
print("instance public dns: %s" % instance_data["PublicDnsName"])
print("instance AvailabilityZone: %s" % instance_data["Placement"]["AvailabilityZone"])

#Wait for the instance to finish setting up
print("Waiting for instance to finish setting up...\n")
time.sleep(10)

#Create the ssh client and run commands
key = paramiko.RSAKey.from_private_key_file(key_filename)
ssh_client = paramiko.SSHClient()
ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

#Load commands from file
cmd_file = open("commands.txt", 'r')
cmds = cmd_file.readlines()
cmd_file.close()

#Open logfile
if os.path.exists("tasks.log"):
    os.remove("tasks.log")
logfile = open("tasks.log", 'w')

try:
    # Open connection to ec2 instance
    ssh_client.connect(hostname= instance_data["PublicIpAddress"], username="ec2-user", pkey=key)

    # Execute a command(cmd) after connecting/ssh to an instance
    for cmd in cmds:
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        logfile.write("> %s" % cmd)
        logfile.write(stdout.read().decode("utf-8")+"\n")

    # close the client connection once the job is done
    ssh_client.close()

except Exception as e:
    print(e)

#Close logfile
logfile.close()

# Terminate the VM we created
# This shuts down the instance and eventually deletes all data associated with it
# It's not enough to just shut down the instance because we are charged for the digital instance's storage space.
print("terminating instance")
instance.terminate()

# Wait for the instance to complete finish terminating
print("waiting until instance is terminated")
instance.wait_until_terminated()

#Delete keypair
response = client.delete_key_pair(
    KeyName= keypair_id,
)
print("keypair delete response: %s\n" % response)


print("finished")