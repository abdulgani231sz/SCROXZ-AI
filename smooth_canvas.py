"""Shared image presentation and Windows DPI setup for the GPU scene."""
from PIL import ImageTk

class SmoothScene:
    def __init__(self,widget):
        self.widget=widget
        self.photo=None
        self.item=None
        self.labels=[]
        self.display_color=widget.display_color
    def __getattr__(self,name):
        return getattr(self.widget,name)
    def __getitem__(self,name):
        return self.widget[name]
    def winfo_width(self):
        return min(820,self.widget.winfo_width())
    def create_text(self,*xy,**kw):
        self.texts.append((xy,kw))
    def present_image(self,image):
        if self.photo is None or self.photo.width()!=self.width or self.photo.height()!=self.height:
            self.photo=ImageTk.PhotoImage(image,master=self.widget)
        else:
            self.photo.paste(image)
        if self.item is None:
            self.item=self.widget.create_image(0,0,anchor='n',image=self.photo)
        self.widget.coords(self.item,self.widget.winfo_width()/2,0)
        self.widget.itemconfigure(self.item,image=self.photo)
        for i,(xy,options) in enumerate(self.texts):
            x,y=xy
            if i>=len(self.labels):
                self.labels.append(self.widget.create_text(x+self.offset,y,**options))
            else:
                self.widget.coords(self.labels[i],x+self.offset,y)
                self.widget.itemconfigure(self.labels[i],**options)


def enable_dpi_awareness():
    """Opt out of Windows bitmap stretching before constructing the first window."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError,OSError):
        pass
