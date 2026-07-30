import configparser
import os

class PropertyReader:

    def property_file_finder(self,path_to_property_file):
                    
        property_file = os.path.join(path_to_property_file)
        configs = configparser.RawConfigParser()
        configs.read(property_file)        
        return configs
