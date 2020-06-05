import datetime
import boto3

ec2_client=boto3.client('ec2','us-east-1')
sns_client = boto3.client('sns','us-east-1')
cw_client = boto3.client('cloudwatch','us-east-1')

maxValue = 9

def lambda_handler(event, context):
    # TODO implement
    
    #print(ec2_client.describe_instances()["Reservations"][0]["Instances"])
    
    #response = ec2_client.describe_instances(Filters=[{"Name":"InstanceId","Values":["i-06154146c2b5b9c93"]}])
    #response = ec2_client.describe_instances(Filters=[{'Name':'instance-state-name','Values':['running']})
    response = ec2_client.describe_instances(Filters=[{'Name':'instance-id','Values':['i-06154146c2b5b9c93']}])
    #response = ec2_client.describe_instances(Filters=[{'Name':'network-interface.addresses.private-ip-address','Values':["xxx.xxx.xxx.xxx"]}])
    #instance_list = sum([reservation['Instances'][0]['NetworkInterfaces'][0]['OwnerId'] for reservation in response['Reservations']], [])
    size_list = [reservation['Instances'][0]['NetworkInterfaces'][0]['OwnerId'] for reservation in response['Reservations']]
 
    total = 0
    
    for size in size_list:
        total = total + float(size)
    
        
    now = datetime.datetime.now() + datetime.timedelta(hours=9)
    print(now)
    
    # �P�ʂ��e���o�C�g�ɕύX
    #if total > 0:
        #total = total / 1000000
    #    total = total / 100000000000
    
    print(total)
    
    if True:
    #if total > maxValue * 0.9:   # 90%�ȏ�̎�
        # SNS�Ń��[�����M���鏈��
        #sns_client.publish(
        #    TopicArn='arn:aws:sns:us-east-1:272114740686:test-notification',
        #    Subject='Test Message',
        #    Message='Test Message Body'
        #)
       # CloudWatch�ɃJ�X�^�����g���N�X���o�͂���
        cw_client.put_metric_data(
			Namespace='redshift',
			MetricData=[
			    {
			        'MetricName': 'TestMetrics',
			        'Dimensions': [
			            {
			                'Name': 'test',
			                'Value': 'snupshot-size3'
			            },
			        ],
			        'Timestamp': datetime.datetime.now(),
			        'StatisticValues': {
			            'SampleCount': 1,
			            'Sum': 2720000,
			            'Minimum': 0,
			            'Maximum': 8000000
			        },
			        'Values': [
			            1.0,
			        ],
			        'Counts': [
			            1.0,
			        ],
			        'Unit': 'Megabytes',
			        'StorageResolution':1
			    },
			]
        )
    
    return
