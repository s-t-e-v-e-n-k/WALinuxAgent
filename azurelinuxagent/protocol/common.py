# Windows Azure Linux Agent
#
# Copyright 2014 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Requires Python 2.4+ and Openssl 1.0+
#
import os
import copy
import re
import json
import xml.dom.minidom
import azurelinuxagent.logger as logger
from azurelinuxagent.utils.textutil import GetNodeTextData
import azurelinuxagent.utils.fileutil as fileutil

class ProtocolError(Exception):
    pass

class ProtocolNotFound(Exception):
    pass

def validata_param(name, val, expectedType):
    if val is None:
        raise ProtocolError("Param {0} is None".format(name))
    if not isinstance(val, expectedType):
        raise ProtocolError("Param {0} type should be {1}".format(name,
                                                                  expectedType))

def set_properties(obj, data):
    validata_param("obj", obj, DataContract)
    validata_param("data", data, dict)

    props = vars(obj)
    for name, val in props.items():
        try:
            newVal = data[name]
        except KeyError:
            continue

        if isinstance(newVal, dict):
            set_properties(val, newVal)
        elif isinstance(newVal, list):
            validata_param("list", val, DataContractList)
            for dataItem in newVal:
               item = val.itemType() 
               set_properties(item, dataItem)
               val.append(item)
        else:
            setattr(obj, name, newVal)

def get_properties(obj):
    validata_param("obj", obj, DataContract)

    data = {}
    props = vars(obj)
    for name, val in props.items():
        if isinstance(val, DataContract):
            data[name] = get_properties(val)
        elif isinstance(val, DataContractList):
            data[name] = []
            for item in val:
                dataItem = get_properties(item)
                data[name].append(dataItem)
        else:
            data[name] = val
    return data

class DataContract(object):
    pass

class DataContractList(list):
    def __init__(self, itemType):
        self.itemType = itemType

class VmInfo(DataContract):
    def __init__(self, subscriptionId=None, vmName=None):
        self.subscriptionId = subscriptionId
        self.vmName = vmName

class Cert(DataContract):
    def __init__(self, name=None, thumbprint=None, certificateDataUri=None):
        self.name = name
        self.thumbprint = thumbprint
        self.certificateDataUri = certificateDataUri

class CertList(DataContract):
    def __init__(self):
        self.certificates = DataContractList(Cert)

class ExtensionSettings(DataContract):
    def __init__(self, name=None, sequenceNumber=None, publicSettings=None,
                 privateSettings=None, certificateThumbprint=None):
        self.name = name
        self.sequenceNumber = sequenceNumber
        self.publicSettings = publicSettings
        self.privateSettings = privateSettings
        self.certificateThumbprint = certificateThumbprint

class ExtensionProperties(DataContract):
    def __init__(self):
        self.version = None
        self.upgradePolicy = None
        self.state = None
        self.extensions = DataContractList(ExtensionSettings)

class ExtensionVersionUri(DataContract):
    def __init__(self):
        self.uri = None

class Extension(DataContract):
    def __init__(self, name=None):
        self.name = name
        self.properties = ExtensionProperties()
        self.versionUris = DataContractList(ExtensionVersionUri)

class ExtensionList(DataContract):
    def __init__(self):
        self.extensions = DataContractList(Extension)

class ExtensionPackageUri(DataContract):
    def __init__(self, uri=None):
        self.uri = uri

class ExtensionPackage(DataContract):
    def __init__(self, version = None):
        self.version = version
        self.uris = DataContractList(ExtensionPackageUri)

class ExtensionPackageList(DataContract):
    def __init__(self):
        self.versions = DataContractList(ExtensionPackage)

class InstanceMetadata(DataContract):
    def __init__(self, deploymentName=None, roleName=None, roleInstanceId=None,
                 containerId=None):
        self.deploymentName = deploymentName
        self.roleName = roleName
        self.roleInstanceId = roleInstanceId
        self.containerId = containerId

class VMProperties(DataContract):
    def __init__(self, certificateThumbprint=None):
        #TODO need to confirm the property name
        self.certificateThumbprint = certificateThumbprint

class ProvisionStatus(DataContract):
    def __init__(self, status=None, subStatus=None, description=None):
        self.status = status
        self.subStatus = subStatus
        self.description = description
        self.properties = VMProperties()

class VMAgentStatus(DataContract):
    def __init__(self, agentVersion=None, status=None, message=None):
        self.agentVersion = agentVersion
        self.status = status
        self.message = message

class ExtensionSubStatus(DataContract):
    def __init__(self, name=None, status=None, code=None, message=None):
        self.name = name
        self.status = status
        self.code = code
        self.message = message

class ExtensionStatus(DataContract):
    def __init__(self, name=None, configurationAppliedTime=None, operation=None,
                 status=None, code=None, sequenceNumber=None):
        self.name = name
        self.configurationAppliedTime = configurationAppliedTime
        self.operation = operation
        self.status = status
        self.code = code
        self.sequenceNumber = sequenceNumber
        self.substatusList = DataContractList(ExtensionSubStatus)

class ExtensionHandlerStatus(DataContract):
    def __init__(self, handlerName=None, handlerVersion=None, status=None,
                 message=None):
        self.handlerName = handlerName
        self.handlerVersion = handlerVersion
        self.status = status
        self.message = message
        self.extensionStatusList = DataContractList(ExtensionStatus)

class VMStatus(DataContract):
    def __init__(self):
        self.vmAgent = VMAgentStatus()
        self.extensionHandlers = DataContractList(ExtensionHandlerStatus)

class TelemetryEventParam(DataContract):
    def __init__(self, name=None, value=None):
        self.name = name
        self.value = value

class TelemetryEvent(DataContract):
    def __init__(self, eventId=None, providerId=None):
        self.eventId = eventId
        self.providerId = providerId
        self.parameters = DataContractList(TelemetryEventParam)

class TelemetryEventList(DataContract):
    def __init__(self):
        self.events = DataContractList(TelemetryEvent)

class Protocol(DataContract):

    def initialize(self):
        raise NotImplementedError()

    def getVmInfo(self):
        raise NotImplementedError()

    def getCerts(self):
        raise NotImplementedError()

    def getExtensions(self):
        raise NotImplementedError()
  
    def getExtensionPackages(self, extension):
        raise NotImplementedError()
    
    def getInstanceMetadata(self):
        raise NotImplementedError()

    def reportProvisionStatus(self, status):
        raise NotImplementedError()

    def reportStatus(self, status):
        raise NotImplementedError()

    def reportEvent(self, event):
        raise NotImplementedError()
